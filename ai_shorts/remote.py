"""Render on another machine over ssh (21 Oct 2026: renders on the laptop ran ffmpeg at 650% CPU
and it was close to cooking; heavy work belongs on a desktop with a GPU).

    python -m ai_shorts tower --video RAW [--video PICKUP] --script scripts/<slug>.md [--framing ..] [--grade ..]

Sends the working copy of the code and any take the render machine lacks (same size and first
megabyte = already there), renders there, and brings the render back to ~/Downloads under the same
name a local render would get, the contact sheet to the video's contact sheets folder and the report
next to the local work dirs.

Where and how is private, so it lives outside the repo in ~/.config/ai-shorts/remote.toml
(or the file AI_SHORTS_REMOTE names). The render machine runs Windows (the commands are cmd):

    host = "my-desktop"                       # ssh host
    code = "C:/ai-shorts"                     # where the code goes; its .venv is made once
    raw = "D:/ai-shorts/raw"                  # takes
    out = "D:/ai-shorts/renders"              # renders
    df_python = "C:/ai-shorts-audio/.venv/Scripts/python.exe"   # optional: DeepFilterNet's own venv
    busy = "..."                              # optional: a command that prints [] when the machine is free

    [r2]                                      # optional: footage through a Cloudflare R2 bucket
    account = "..."
    bucket = "..."
    key_id = "..."                            # a local command that prints the access key id
    secret = "..."                            # a local command that prints the secret
    env_file = "C:/ai-shorts/.r2"             # where the render machine keeps that key

Footage goes through R2 when it is set up: over ssh it managed ~0.5 MB/s and a 1.7 GB
take took an hour, R2 ~13 MB/s up and 30 s down (21 Oct 2026). Give the bucket a short lifecycle;
each take is deleted once the fetch is over anyway, failed or not.
"""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import threading
import time
import tomllib

from .config import FRAMINGS, GRADES, Config
from .media import file_key
from .pipeline import OUTPUT_ROOT, PROJECT_ROOT, REVIEW_DIR, next_version, release, render_name, reserve
from .spec import load_spec

SETTINGS = Path(os.environ.get("AI_SHORTS_REMOTE") or Path.home() / ".config" / "ai-shorts" / "remote.toml")
PACKAGES = "openai-whisper boto3"
TORCH = "torch --index-url https://download.pytorch.org/whl/cu126"   # CUDA 12 build
SAFE = re.compile(r"[A-Za-z0-9._ +-]+")   # fine inside a quoted cmd.exe argument: no " % ^ & ! < > |


@dataclass(frozen=True)
class R2:
    account: str
    bucket: str
    key_id: str        # local commands that print the keys
    secret: str
    env_file: str


@dataclass(frozen=True)
class Remote:
    host: str
    code: str
    raw: str
    out: str
    df_python: str = ""
    busy: str = ""
    r2: R2 | None = None


def load_settings(path: Path = SETTINGS) -> Remote:
    if not path.exists():
        raise SystemExit(f"[tower] no settings at {path}: see the top of ai_shorts/remote.py for what goes in it")
    d = tomllib.loads(path.read_text())
    r2 = d.pop("r2", None)
    return Remote(**d, r2=R2(**r2) if r2 else None)


def _keys(r2: R2) -> tuple[str, str] | None:
    """The R2 key from the local commands, or None when either prints nothing."""
    out = []
    for cmd in (r2.key_id, r2.secret):
        res = subprocess.run(shlex.split(cmd), capture_output=True, text=True)
        out.append(res.stdout.strip() if res.returncode == 0 else "")
    return (out[0], out[1]) if all(out) else None


def r2_client(account: str, key_id: str, secret: str):
    import boto3
    from botocore.config import Config as BotoConfig
    return boto3.client("s3", endpoint_url=f"https://{account}.r2.cloudflarestorage.com",
                        aws_access_key_id=key_id, aws_secret_access_key=secret, region_name="auto",
                        config=BotoConfig(retries={"max_attempts": 10, "mode": "adaptive"}))


def _transfer():
    from boto3.s3.transfer import TransferConfig
    return TransferConfig(multipart_chunksize=64 << 20, max_concurrency=8)


def win(path: str) -> str:
    return path.replace("/", "\\")


def ident(path: Path) -> str | None:
    """Size and a hash of the first megabyte (media.file_key without the name), None for no file:
    the same on both machines and quick on a 1.7 GB take."""
    return file_key(path).split("|", 1)[1] if Path(path).is_file() else None


class Machine:
    """ssh and scp to the render machine."""

    def __init__(self, s: Remote):
        self.s = s

    def ssh(self, cmd: str, timeout: float = 120, stream: bool = False, stdin: str | None = None) -> str:
        """One command in the render machine's cmd shell."""
        argv = ["ssh", "-o", "ConnectTimeout=15", self.s.host, cmd]
        if stream:   # renders print as they go
            p = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            # the deadline holds while output flows or the pipe hangs: reading to the end before
            # wait(timeout) left a stalled render with no deadline at all (audit2 codex-004)
            expired = threading.Event()
            watchdog = threading.Timer(timeout, lambda: (expired.set(), p.kill()))
            watchdog.daemon = True
            watchdog.start()
            lines = []
            try:
                for line in p.stdout:
                    print(line, end="", flush=True)
                    lines.append(line)
                p.wait()
            finally:
                watchdog.cancel()
                if p.poll() is None:     # interrupted while reading: no ssh left running
                    p.kill()
                    p.wait()
                p.stdout.close()
            if expired.is_set():
                raise subprocess.TimeoutExpired(argv, timeout, output="".join(lines))
            if p.returncode:
                raise RuntimeError(f"tower command failed ({p.returncode})")
            return "".join(lines)
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, input=stdin)
        if r.returncode:
            raise RuntimeError(f"tower: {cmd[:80]}... failed ({r.returncode}): {(r.stderr or r.stdout)[-800:]}")
        return r.stdout

    def scp_to(self, src: str, dst: str, timeout: float = 1800) -> None:
        subprocess.run(["scp", "-q", "-o", "ConnectTimeout=15", src, f"{self.s.host}:{dst}"], check=True,
                       timeout=timeout)

    def scp_from(self, src: str, dst: str, timeout: float = 1800) -> None:
        subprocess.run(["scp", "-q", "-o", "ConnectTimeout=15", f"{self.s.host}:{src}", dst], check=True,
                       timeout=timeout)

    def size(self, path: str) -> int | None:
        out = self.ssh(f'if exist "{win(path)}" (for %I in ("{win(path)}") do @echo %~zI) else (echo none)')
        out = out.strip().splitlines()[-1] if out.strip() else "none"
        return int(out) if out.isdigit() else None

    def ident(self, paths: list[str]) -> list[str | None]:
        """ident() of each file, worked out on the render machine by its venv's python."""
        args = " ".join(f'"{win(p)}"' for p in paths)
        out = self.ssh(f'cd /d "{win(self.s.code)}" && .venv\\Scripts\\python -m ai_shorts.remote ident {args}')
        return json.loads(out.strip().splitlines()[-1])

    def python(self) -> str:
        return f'"{win(self.s.code)}\\.venv\\Scripts\\python.exe"'


def deploy(m: Machine) -> None:
    """The working copy of every tracked file (uncommitted edits included), into the code folder;
    the venv is made once and kept."""
    code = win(m.s.code)
    with tempfile.TemporaryDirectory() as tmp:
        tar = Path(tmp) / "ai-shorts.tgz"
        files = subprocess.run(["git", "-C", str(PROJECT_ROOT), "ls-files", "-z"], capture_output=True,
                               check=True).stdout
        subprocess.run(["tar", "--null", "-T", "-", "-czf", str(tar)], input=files, cwd=PROJECT_ROOT, check=True)
        m.ssh(f'if not exist "{code}" mkdir "{code}"')
        m.scp_to(str(tar), f"{m.s.code}/ai-shorts.tgz")
    m.ssh(f'cd /d "{code}" && tar -xzf ai-shorts.tgz && del ai-shorts.tgz')
    ready = m.ssh(f'cd /d "{code}" && (.venv\\Scripts\\python -c "import whisper, torch, cv2, boto3; '
                  f'assert torch.cuda.is_available(); print(1)" 2>nul || echo missing)')
    if "missing" in ready:      # first run, or one that died half way: the import is the test
        print("[tower] setting up the venv (a few minutes)", flush=True)
        # --no-warn-script-location: pip's PATH check died on a junction it could not traverse
        m.ssh(f'cd /d "{code}" && (if not exist .venv py -3.12 -m venv .venv) && .venv\\Scripts\\python -m pip '
              f'install -q --no-warn-script-location -U pip && .venv\\Scripts\\python -m pip install -q '
              f'--no-warn-script-location {TORCH} && .venv\\Scripts\\python -m pip install -q '
              f'--no-warn-script-location -e . {PACKAGES}', timeout=3600)
    else:
        m.ssh(f'cd /d "{code}" && .venv\\Scripts\\python -m pip install -q --no-warn-script-location -e . --no-deps',
              timeout=600)


def send_take(m: Machine, video: Path) -> str:
    """The take onto the render machine: through R2 when it is set up and the key prints, else scp.
    A take is known by its content, not its name: two files of one name and size shared one copy
    and one R2 key, so the second rendered the first's footage (audit2 codex-001). One already there
    is not sent again, under its plain name (every take sent before 23 Oct 2026) or its keyed one."""
    fk = file_key(video)
    want = fk.split("|", 1)[1]
    name = f"{video.stem}-{hashlib.sha1(fk.encode()).hexdigest()[:10]}{video.suffix}"   # its R2 key too
    plain, dst = f"{m.s.raw}/{video.name}", f"{m.s.raw}/{name}"
    for path, there in zip((plain, dst), m.ident([plain, dst])):
        if there == want:
            return path
    size = video.stat().st_size
    m.ssh(f'if not exist "{win(m.s.raw)}" mkdir "{win(m.s.raw)}"')
    r2 = m.s.r2
    keys = _keys(r2) if r2 else None
    if keys:
        client, obj = r2_client(r2.account, *keys), f"raw/{name}"
        t0 = time.time()
        print(f"[tower] {video.name} ({size / 1e9:.1f} GB) to R2", flush=True)
        try:
            client.upload_file(str(video), r2.bucket, obj, Config=_transfer())
            t1 = time.time()
            print(f"[tower] up in {t1 - t0:.0f}s ({size / 1e6 / max(1, t1 - t0):.1f} MB/s); tower fetching", flush=True)
            # the key goes over ssh's stdin, never on a command line, and every time: written only
            # when missing, a rotated key never reached the render machine (audit2 claude-006)
            m.ssh(f'{m.python()} -c "import sys,pathlib; pathlib.Path(r\'{win(r2.env_file)}\')'
                  f'.write_text(sys.stdin.read())"', timeout=60, stdin=f"{keys[0]}\n{keys[1]}\n")
            m.ssh(f'cd /d "{win(m.s.code)}" && .venv\\Scripts\\python -m ai_shorts.remote fetch {r2.account} '
                  f'{r2.bucket} "{obj}" "{win(dst)}" "{win(r2.env_file)}"', timeout=3600)
            print(f"[tower] down in {time.time() - t1:.0f}s", flush=True)
        finally:   # a failed fetch left the raw take, camera metadata and all, in the bucket (audit2 k3-006)
            try:
                client.delete_object(Bucket=r2.bucket, Key=obj)
            except Exception as e:
                print(f"[tower] WARNING: {obj} is still in the bucket ({e}): delete it there", flush=True)
    else:
        print(f"[tower] sending {video.name} ({size / 1e9:.1f} GB) over ssh (no R2 key: slow)", flush=True)
        m.scp_to(str(video), dst, timeout=3600)
    if m.ident([dst]) != [want]:
        raise RuntimeError(f"{video.name} arrived different (size or first megabyte)")
    return dst


def bring_home(m: Machine, src: str, dst: Path) -> None:
    """One file from the render machine: copied under a partial name, checked against the size there,
    then renamed. scp straight into the reserved name left a cut-off mp4 under the render's real
    name when the copy died, and release() keeps a non-empty file (audit2 codex-002)."""
    want = m.size(src)
    if not want:
        raise RuntimeError(f"{src} is missing or empty on the render machine")
    part = dst.with_name(f"{dst.stem}.{os.getpid()}.partial{dst.suffix}")
    try:
        m.scp_from(src, str(part))
        if (got := part.stat().st_size) != want:
            raise RuntimeError(f"{dst.name} came back at {got} of {want} bytes")
        os.replace(part, dst)
    finally:
        part.unlink(missing_ok=True)


def fetch(account: str, bucket: str, key: str, dst: str, env_file: str) -> None:
    """On the render machine: one object from R2 to a local file, with the key from env_file."""
    key_id, secret = Path(env_file).read_text().split()[:2]
    r2_client(account, key_id, secret).download_file(bucket, key, dst, Config=_transfer())


def check_inputs(videos: list[Path], script: Path, slug: str, framing: str | None, grade: str | None) -> str:
    """Everything the render machine's commands are built from, checked before anything is reserved
    or sent: take names, the slug and the presets went into cmd.exe as they came, where a quote or a
    %VAR% rewrites the command (audit2 codex-003, claude-012). Returns the script's path in the repo."""
    allowed = "letters, digits, spaces and ._+- only"
    for v in videos:
        if not v.is_file():
            raise SystemExit(f"[tower] no take at {v}")
        if not SAFE.fullmatch(v.name):
            raise SystemExit(f"[tower] rename {v.name!r}: take names go into the render machine's commands ({allowed})")
    if not SAFE.fullmatch(slug):
        raise SystemExit(f"[tower] the script's slug {slug!r} names the render ({allowed})")
    if framing and framing not in FRAMINGS:
        raise SystemExit(f"[tower] no framing {framing!r}: one of {', '.join(sorted(FRAMINGS))}")
    if grade and grade not in GRADES:
        raise SystemExit(f"[tower] no grade {grade!r}: one of {', '.join(GRADES)}")
    try:
        rel = script.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        raise SystemExit(f"[tower] {script} is outside the repo: the render machine only gets the repo's files") \
            from None
    if not all(SAFE.fullmatch(part) for part in rel.split("/")):
        raise SystemExit(f"[tower] rename {rel!r} ({allowed})")
    # deploy sends tracked files only: an untracked script failed on the tower after the upload (audit2 claude-005)
    if subprocess.run(["git", "-C", str(PROJECT_ROOT), "ls-files", "--error-unmatch", rel],
                      capture_output=True).returncode:
        raise SystemExit(f"[tower] {rel} is not in git: git add it (the render machine only gets tracked files)")
    return rel


def render(videos: list[Path], script: Path, framing: str | None, grade: str | None, force: bool = False,
           settings: Remote | None = None) -> Path:
    spec, cfg = load_spec(script), Config()
    rel = check_inputs(videos, script, spec.slug, framing, grade)
    m = Machine(settings or load_settings())
    if m.s.busy:
        busy = m.ssh(m.s.busy, timeout=60).strip()
        if busy not in ("[]", "") and not force:
            raise SystemExit(f"[tower] not rendering: busy with {busy} (add --force to render anyway)")
    label = (framing or cfg.framing) + (f" {grade} grade" if grade and grade != "none" else "")
    n = next_version(spec.slug, REVIEW_DIR, OUTPUT_ROOT)
    while not reserve(review := REVIEW_DIR / render_name(spec.slug, n, label)):
        n += 1           # a local render took that number while this one was starting
    try:
        return _render(m, videos, rel, spec, review, framing, grade)
    except BaseException:
        release(review)  # a failed render gives its name back
        raise


def _render(m: Machine, videos: list[Path], script: str, spec, review: Path, framing: str | None,
            grade: str | None) -> Path:
    name = review.name
    deploy(m)
    remote_videos = [send_take(m, v) for v in videos]
    out = win(m.s.out)
    m.ssh(f'if not exist "{out}" mkdir "{out}"')
    # the number is ours here, so a file under it on the render machine is a try that never came home
    # (killed, or its copy failed and gave the name back): the render there refuses to overwrite it,
    # and a retry after a failed copy hit that every time (audit2 claude-005)
    if m.size(f"{m.s.out}/{name}") is not None:
        m.ssh(f'del "{out}\\{name}"')
    args = " ".join(f'--video "{win(v)}"' for v in remote_videos)
    args += f' --script "{win(script)}" --out "{out}\\{name}"'
    args += (f" --framing {framing}" if framing else "") + (f" --grade {grade}" if grade else "")
    env = f'set "AI_SHORTS_DF_PYTHON={win(m.s.df_python)}" && ' if m.s.df_python else ""
    log = m.ssh(f'{env}cd /d "{win(m.s.code)}" && .venv\\Scripts\\python -m ai_shorts render {args}',
                timeout=7200, stream=True)
    bring_home(m, f"{m.s.out}/{name}", review)
    sheets = OUTPUT_ROOT / spec.slug / "contact sheets"
    sheets.mkdir(parents=True, exist_ok=True)
    stem = name[:-4]
    bring_home(m, f"{m.s.out}/{stem} contact sheet.png", sheets / f"{stem} contact sheet.png")
    work = re.search(r"work dir (\S.*)$", log, re.M)
    if work:
        local = PROJECT_ROOT / "out" / "tower" / stem
        local.mkdir(parents=True, exist_ok=True)
        # this render's own report: renders of one take share a work dir and its report.json
        bring_home(m, f"{work.group(1).strip().replace(chr(92), '/')}/reports/{stem}.json", local / "report.json")
        problems = json.loads((local / "report.json").read_text()).get("self_check", [])
        print(f"[tower] self-check: {'clean' if not problems else f'{len(problems)} to listen to'}")
    print(f"[tower] done: {review}")
    return review


def main(argv=None) -> int:
    import argparse
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["fetch"]:          # render-machine side of send_take
        fetch(*argv[1:6])
        return 0
    if argv[:1] == ["ident"]:          # render-machine side of send_take
        print(json.dumps([ident(Path(p)) for p in argv[1:]]))
        return 0
    ap = argparse.ArgumentParser(prog="ai_shorts tower")
    ap.add_argument("--video", required=True, type=Path, action="append")
    ap.add_argument("--script", required=True, type=Path)
    ap.add_argument("--framing", choices=sorted(FRAMINGS))
    ap.add_argument("--grade", choices=list(GRADES))
    ap.add_argument("--force", action="store_true", help="render even while the machine says it is busy")
    a = ap.parse_args(argv)
    render([v.expanduser() for v in a.video], a.script.expanduser().resolve(), a.framing, a.grade, a.force)
    return 0


if __name__ == "__main__":
    sys.exit(main())
