# 003: Can AI pick my best stream clips?

My stream pipeline cuts candidate clips out of every stream, and my editor keeps or bins each
one. This folder has the prompt that now decides which candidates he sees, and how it was tested.

## The detector

The clipper finds moments with 14 signals: the transcript, chat spikes, loudness, pitch,
laughter, my face on camera, each against that stream's own baseline. For three months it also
tried to learn which signals my editor rewards, from his grades.

Then I checked it against 336 clips he had already graded. The detector's score predicted his
call with an AUC of 0.498, and the learned weights 0.505. An AUC of 0.5 is a coin flip, so three
months of learning learned nothing. Every signal fires on most candidates, because firing is how
a moment becomes a candidate, so none of them tells a good clip from a bad one.

## The judge

`prompt.txt` is the whole method. The model gets 48 of the editor's past decisions as examples
(24 kept, 24 rejected, at most 4 from any one stream) and then one new clip. It sees only the game
name and the first 600 characters of the transcript, never the video, and answers with the chance
he would keep it.

On 287 clips it had not seen as examples, `claude-opus-5` scored an AUC of 0.76, and 0.763 on a
rerun. AUC 0.76 means: give it one clip he kept and one he binned, and it ranks the kept one
higher about three times out of four. Adding the detector's signals to the prompt made it worse
(0.71).

## How the pipeline uses it

Every candidate is scored. About 60% of a stream reaches the editor: mostly the top scores, plus
a blind random draw for a fifth of the slots, so the judge also gets graded on clips it did not
pick. The examples are rebuilt from his latest grades every run, so every grade changes the next
day's judging. A frozen copy of the first examples scores the same clips alongside, to show
whether that rebuild is actually learning anything.

## Files

- `prompt.txt`: the prompt. `{examples}` is replaced by the example clips, each as
  `<example verdict="KEPT">` (or `"REJECTED"`) with its game and transcript.
- `judge.py`: builds the prompt from your own graded clips, scores new ones, and measures AUC on
  held-out grades.

```
pip install anthropic
export ANTHROPIC_API_KEY=...
python judge.py test graded.jsonl --examples 48 --out test-scores.jsonl
python judge.py score graded.jsonl new.jsonl
```

Each line of `graded.jsonl` is `{"game": "...", "transcript": "...", "kept": true, "stream": "..."}`.
`stream` is optional. With it, `judge.py` takes at most 4 examples from any one stream, as the
pipeline does. Without it, the examples are only balanced between kept and rejected.

`test` makes one Opus call per held-out clip, and says how many before it starts. `--max-calls`
lowers that. Each score is saved to `--out` as it lands, so a stopped run keeps what it paid for.
A reply that isn't just a whole number from 0 to 100 counts as failed, never as a score. The
summary gives how many clips were attempted, scored and failed, and the AUC is over the scored
ones.

The prompt the pipeline runs names the editor and the streamer; this copy is generic. The graded
clips are not included: they are my editor's decisions on stream footage.
