# Speech coverage · 1.3.2

One complete Windows x64 ZIP includes every bundled voice. Female Persian Edge is preferred for Farsi and Dari; Dari pronunciation is approximate. The working local Tigrinya, Sorani and Oromo routes remain first. Kurmanji tries Turkish speech before its robotic reserve. Sindhi tries approximate Urdu speech before its robotic reserve. Online substitutes retain complete-passage checks and explicit approximation labels.

- Dedicated new local voices: Tigrinya, Oromo, Sorani; Somali has a limited reserve.
- Dari: female Persian Edge first, bundled Persian Piper reserve, then exact Windows/basic Persian. Pronunciation is explicitly labelled approximate.
- Kurmanji and Sindhi: online pronunciation substitutes first, robotic fallback last; neither substitute is a native voice.
- If a neural voice cannot read the whole passage, the app tries an available complete reserve. Recovered online pronunciation substitutes are now available for Tigrinya and Sorani. It never knowingly plays only the supported fragment.
- **Preparing voice** changes to **Speaking** when complete audio is ready. A robotic or approximate fallback is identified in the status line.
- **Halt Voice** / **Esc** stops preparation or playback. A damaged/missing pack leaves other routes available.

[Every language and route](../APP-CAPABILITIES.csv) · [Measured results and remaining gaps](../verification/gap-validation-20261012.md)


[Current changes, measurements and limits](../verification/speech-hotfix-1.3.2.md). Earlier 1.3.1 measurements are historical and do not describe these revised routes.
