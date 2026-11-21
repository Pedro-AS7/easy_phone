# easy_phone

An AI assistant that uses an Android phone the way a person does (opens apps, reads the screen, taps, scrolls, types),
built first of all as a **patient tech helper for people who struggle with their phone**, such as older adults: "how do
I...", "the text is too small", "an icon disappeared". By default the person taps and the assistant points, explains and
waits; an option lets the assistant do it while explaining. Everyday tasks (a message, a call, a route) come second.

> Personal project, in active development. The UI, the code comments and the rest of the documentation are in
> Brazilian Portuguese. The Python package and the Android package are still called `lmphone` (the project's earlier
> name).

## The central rule: personal data never leaves the phone unmasked

A **local AI** understands the request and masks the personal data in it and on every screen; a **cloud model** plans
the steps seeing only fake values. The real values come back only on the device, when typing or showing the answer.

```
request -> local AI judges the request ┐
        -> accessibility on            ├ in parallel
        -> cloud model writes a plan   ┘ (masked request)
        -> loop: read the screen -> decide (exact label | small local model | help from the cloud model,
                 with a reduced, masked screen) -> act -> check the effect -> ... -> goal checked on the screen
        -> answer to the user -> accessibility off
```

- The screen is read as text from the accessibility tree, never as pixels: text can be masked, pixels can't.
- Fixed rules (names, e-mails, phone numbers, CPF, cards, passwords said in the request...) and a vault with the
  phone's contacts and accounts work even without the local AI.
- Local models: two small encoders on top of `intfloat/multilingual-e5-small`, trained on phone screens (entity
  tagging and request intent; picking the control that matches a name), exported to ONNX and run on the CPU
  (5 to 30 ms per call), on the PC or inside the Android app.
- Actions that can't be undone (send, buy, pay, delete, publish, call) wait for the user's confirmation.
- Accessibility is on only during a task: some banking apps lock the phone when they see a third-party accessibility
  service.

## What's in the repository

| Path | What |
|---|---|
| `lmphone/` | The PC prototype (Python 3.12, standard library only): a service that drives the phone over ADB, the executor, masking, the local AI client, cache and app maps |
| `android/` | The Android app (Kotlin + Jetpack Compose): accessibility service, floating live-mode bar, voice, the assistant panel, the small models on the device (`modelos/`) and the "brain" translated to Kotlin (`cerebro/`), checked against the Python one |
| `android/app/src/loja` | The Play Store variant: it **only teaches** (the agent never acts); a build check fails if any action API shows up in it |
| `servidor/` | The small server that holds the cloud model key for the store variant (monthly quota per install, no content stored) |
| `tools/` | Training of the small models, export to ONNX, sending models and the brain to the phone |
| `tests/` | Unit tests, the phone test suite, a simulator that runs whole guides without a phone, and the frozen evaluation set (all fictional data) |
| `docs/` | Plans and the full history of decisions and measurements |

`CLAUDE.md` describes the current state, how to run every part and the decisions in force; it is also the instruction
file for AI coding agents working on the project.

## Running

You need an Android phone with USB (or wireless) debugging, `adb`, Python 3.12 and an
[OpenRouter](https://openrouter.ai) key in `.env` (`OPENROUTER_API_KEY=...`). The small local models are not in the
repository (`data/modelos/`); they are trained with the scripts in `tools/treino/`.

```sh
python3.12 -m venv .venv
.venv/bin/python -m unittest discover -s tests   # unit tests (no phone needed)
.venv/bin/python -m tests.simulador -v           # store-variant guides in the simulator, no phone needed
./run.sh "Turn on dark mode"                     # one task on the phone
./run.sh --conversa                              # chat with the assistant from the terminal
android/build.sh loja                            # build and install the store variant (JDK 17, Android SDK 36)
```

See `CLAUDE.md` ("Como rodar") for every command, including the Windows equivalents.

## Contributing

Issues and pull requests are welcome, in Portuguese or English; see [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[GPL-3.0](LICENSE).
