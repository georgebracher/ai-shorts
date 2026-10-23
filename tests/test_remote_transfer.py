"""The tower route against a fake render machine: a folder standing in for its disks, commands
matched by pattern, the tower-side halves (ident, fetch) run through remote.main as the real one
runs them. No ssh, no network, no R2."""
import contextlib
import io
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

from ai_shorts import remote
from ai_shorts.remote import R2, Remote

RAW = "D:/r"
R2_SET = R2("acct", "bkt", "unused", "unused", "C:/c/.r2")
WORK = "C:\\c\\out\\work\\clip-0123456789"


class FakeTower(remote.Machine):
    def __init__(self, root: Path, r2: R2 | None = None):
        super().__init__(Remote("box", "C:/c", RAW, "D:/o", busy="busy-check", r2=r2))
        self.root = root
        self.calls: list[str] = []      # every touch: ssh commands and scp both ways
        self.stdins: list[str] = []
        self.cut = ""       # how the next copy home of a render goes wrong: dropped, short, refused
        self.fail_fetch = False

    def at(self, path: str) -> Path:    # D:\r\a.MP4 -> <root>/D/r/a.MP4
        return self.root / path.replace("\\", "/").replace(":", "", 1)

    def put(self, path: str, data: bytes) -> None:
        self.at(path).parent.mkdir(parents=True, exist_ok=True)
        self.at(path).write_bytes(data)

    def tower_side(self, argv: list[str]) -> str:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            remote.main(argv)
        return buf.getvalue()

    def ssh(self, cmd, timeout=120, stream=False, stdin=None):
        self.calls.append(cmd)
        if stdin is not None:
            self.stdins.append(stdin)
        quoted = re.findall(r'"([^"]*)"', cmd)
        if "write_text(sys.stdin.read())" in cmd:
            self.put(re.search(r"r'([^']+)'", cmd).group(1), stdin.encode())
            return ""
        if "(echo ok)" in cmd:
            return "ok\n" if self.at(quoted[0]).is_file() else "none\n"
        if " ai_shorts.remote fetch " in cmd:
            if self.fail_fetch:
                raise RuntimeError("tower: fetch failed (1)")
            account, bucket = re.search(r"fetch (\S+) (\S+) ", cmd).groups()
            return self.tower_side(["fetch", account, bucket, quoted[1], *[str(self.at(p)) for p in quoted[2:4]]])
        if " ai_shorts.remote ident " in cmd:
            return self.tower_side(["ident", *[str(self.at(p)) for p in quoted[1:]]])
        if "%~zI" in cmd:
            p = self.at(quoted[0])
            return f"{p.stat().st_size}\n" if p.is_file() else "none\n"
        if " mkdir " in cmd:
            self.at(quoted[-1]).mkdir(parents=True, exist_ok=True)
        if cmd.startswith("del "):
            self.at(quoted[0]).unlink()
        if " -m ai_shorts render " in cmd:
            return self.render(cmd)
        return ""

    def render(self, cmd: str) -> str:
        """What python -m ai_shorts render leaves on the tower: the render, its sheet, its report."""
        out = self.at(re.search(r'--out "([^"]+)"', cmd).group(1))
        if out.is_file() and out.stat().st_size:        # pipeline.claim refuses
            raise RuntimeError("tower command failed (1)")
        footage = b"".join(self.at(v).read_bytes()[:8] for v in re.findall(r'--video "([^"]+)"', cmd))
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(footage * 5000)
        out.with_name(f"{out.stem} contact sheet.png").write_bytes(b"png")
        self.put(f"{WORK}/reports/{out.stem}.json", json.dumps({"self_check": []}).encode())
        return f"[ai-shorts] source 1080x1920 30.00fps 10.0s; work dir {WORK}\n"

    def scp_to(self, src, dst, timeout=1800):
        self.calls.append(f"scp_to {dst}")
        self.put(dst, Path(src).read_bytes())

    def scp_from(self, src, dst, timeout=1800):
        self.calls.append(f"scp_from {src}")
        data = self.at(src).read_bytes()
        if self.cut and src.endswith(".mp4"):
            how, self.cut = self.cut, ""
            if how != "refused":                         # refused: scp never got to write
                Path(dst).write_bytes(data[: len(data) // 2])
            if how != "short":                           # short: ends early without an error
                raise subprocess.CalledProcessError(1, "scp")
            return
        Path(dst).write_bytes(data)


class FakeBucket:
    """R2 as a dict; each client keeps the key it was made with."""
    def __init__(self):
        self.objects: dict[str, bytes] = {}
        self.deleted: list[str] = []
        self.fetched_with: list[tuple[str, str]] = []

    def client(self, account, key_id, secret):
        bucket = self

        class Client:
            def upload_file(self, src, name, key, Config=None):
                bucket.objects[key] = Path(src).read_bytes()

            def download_file(self, name, key, dst, Config=None):
                bucket.fetched_with.append((key_id, secret))
                Path(dst).write_bytes(bucket.objects[key])

            def delete_object(self, Bucket, Key):
                bucket.deleted.append(Key)
                bucket.objects.pop(Key, None)
        return Client()


@pytest.fixture
def bucket(monkeypatch):
    b = FakeBucket()
    monkeypatch.setattr(remote, "r2_client", b.client)
    monkeypatch.setattr(remote, "_keys", lambda r2: ("key-id-2", "SECRET-2"))
    return b


@pytest.fixture
def script(tmp_path, monkeypatch):
    """A git repo with one tracked script, standing in for the project."""
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    path = root / "scripts" / "clip-test.md"
    path.write_text("---\nslug: clip-test\ntitle: Clip test\n---\nHello there.\n")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "add", "scripts"], check=True)
    monkeypatch.setattr(remote, "PROJECT_ROOT", root)
    return path


@pytest.fixture
def tower(tmp_path, monkeypatch):
    """remote.render() gets this tower; deploy is a recorded no-op."""
    t = FakeTower(tmp_path / "tower")
    monkeypatch.setattr(remote, "Machine", lambda s: t)
    monkeypatch.setattr(remote, "deploy", lambda m: m.calls.append("deploy"))
    return t


def take(path: Path, fill: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(fill * 4096)
    return path


def test_same_name_takes_stay_apart(tmp_path):
    """Two cameras' clip.MP4 of one size: the one already on the tower under its plain name is
    reused without a re-upload, the other goes under a keyed name and renders its own footage."""
    tower = FakeTower(tmp_path / "tower")
    a, b = take(tmp_path / "a" / "clip.MP4", b"A"), take(tmp_path / "b" / "clip.MP4", b"B")
    tower.put(f"{RAW}/clip.MP4", a.read_bytes())      # sent before takes had keyed names
    da, db = remote.send_take(tower, a), remote.send_take(tower, b)
    assert da == f"{RAW}/clip.MP4" and db != da and re.fullmatch(rf"{RAW}/clip-[0-9a-f]{{10}}\.MP4", db)
    assert [c for c in tower.calls if c.startswith("scp_to")] == [f"scp_to {db}"]
    assert tower.at(db).read_bytes() == b.read_bytes()
    assert remote.send_take(tower, b) == db and len([c for c in tower.calls if c.startswith("scp_to")]) == 1


@pytest.mark.parametrize("how", ["dropped", "short"])
def test_cut_off_copy_leaves_no_render_behind(tmp_path, script, tower, how):
    """scp dying half way, or ending early without an error, leaves nothing under the render's
    name: the reservation is given back and no partial stays in Downloads."""
    clip = take(tmp_path / "clip.MP4", b"A")
    tower.cut = how
    with pytest.raises((subprocess.CalledProcessError, RuntimeError)):
        remote.render([clip], script, None, None, settings=tower.s)
    assert list((tmp_path / "Downloads").iterdir()) == []


@pytest.mark.parametrize("bad", ["take name", "slug", "framing", "grade", "outside the repo"])
def test_unsafe_input_stops_before_the_tower(tmp_path, script, tower, bad):
    """A quote, % or & in a take name or the slug, a framing or grade that is no preset, or a script
    the render machine never gets: refused before the busy check, a reservation or a deploy."""
    clip = take(tmp_path / ('clip "50%" & x.MP4' if bad == "take name" else "clip.MP4"), b"A")
    if bad == "slug":
        script.write_text("---\nslug: 'x\" & del /q C:\\* & \"'\ntitle: T\n---\nHello there.\n")
    if bad == "outside the repo":
        script = tmp_path / "elsewhere.md"
        script.write_text("---\nslug: clip-test\ntitle: T\n---\nHello there.\n")
    with pytest.raises(SystemExit, match=r"\[tower\]"):
        remote.render([clip], script, "medium & calc" if bad == "framing" else None,
                      "light|calc" if bad == "grade" else None, settings=tower.s)
    assert tower.calls == [] and not (tmp_path / "Downloads").exists()


def test_stream_deadline_holds_while_the_command_hangs(monkeypatch):
    """A render that prints a line and then hangs is stopped at its deadline, not at its end."""
    real, procs = subprocess.Popen, []

    def hung(argv, **kw):          # in place of ssh: a command that never finishes on its own
        procs.append(real([sys.executable, "-c", "import time; print('frame 1', flush=True); time.sleep(20)"], **kw))
        return procs[-1]

    monkeypatch.setattr(remote.subprocess, "Popen", hung)
    t0 = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired) as e:
        remote.Machine(Remote("box", "C:/c", RAW, "D:/o")).ssh("render", timeout=1, stream=True)
    assert time.monotonic() - t0 < 10 and "frame 1" in e.value.output
    assert procs[0].poll() is not None      # killed, not left running


def test_retry_after_a_failed_copy_gets_its_number_back(tmp_path, script, tower):
    """A copy home that never started gives the name back; the retry takes the same number and the
    finished file the tower holds under it no longer blocks the render."""
    clip = take(tmp_path / "clip.MP4", b"A")
    tower.cut = "refused"
    with pytest.raises(subprocess.CalledProcessError):
        remote.render([clip], script, None, None, settings=tower.s)
    out = remote.render([clip], script, None, None, settings=tower.s)
    assert out.name == "clip-test v1 medium - AI Shorts.mp4"
    assert out.read_bytes() == tower.at(f"D:/o/{out.name}").read_bytes()
    sheets = tmp_path / "Downloads" / "AI Shorts" / "clip-test" / "contact sheets"
    assert (sheets / f"{out.stem} contact sheet.png").is_file()
    assert (tmp_path / "repo" / "out" / "tower" / out.stem / "report.json").is_file()


def test_untracked_script_stops_before_the_upload(tmp_path, script, tower):
    new = script.with_name("clip-test-2.md")
    new.write_text(script.read_text())
    with pytest.raises(SystemExit, match="git add"):
        remote.render([take(tmp_path / "clip.MP4", b"A")], new, None, None, settings=tower.s)
    assert tower.calls == []


def test_failed_fetch_still_empties_the_bucket(tmp_path, bucket):
    pytest.importorskip("boto3")   # the R2 route needs the remote extra
    tower = FakeTower(tmp_path / "tower", r2=R2_SET)
    tower.fail_fetch = True
    with pytest.raises(RuntimeError, match="fetch failed"):
        remote.send_take(tower, take(tmp_path / "clip.MP4", b"A"))
    assert bucket.objects == {} and re.fullmatch(r"raw/clip-[0-9a-f]{10}\.MP4", bucket.deleted[0])


def test_rotated_r2_key_reaches_the_tower(tmp_path, bucket):
    pytest.importorskip("boto3")   # the R2 route needs the remote extra
    """The tower already holds a key, the one from before a rotation: it is rewritten (over stdin)
    and its fetch uses the new one."""
    tower = FakeTower(tmp_path / "tower", r2=R2_SET)
    tower.put("C:/c/.r2", b"key-id-1\nSECRET-1\n")
    clip = take(tmp_path / "clip.MP4", b"A")
    dst = remote.send_take(tower, clip)
    assert tower.at(dst).read_bytes() == clip.read_bytes() and bucket.objects == {}
    assert bucket.fetched_with == [("key-id-2", "SECRET-2")]
    assert not any("SECRET" in c for c in tower.calls)
