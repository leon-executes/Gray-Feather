# 1.3.2 · Speech usability repair

The 1.3.1 test installation initially lacked its companion neural models. Installing them restored Tigrinya, Sorani and other working local voices. This release puts **all models in one conventional Windows ZIP**.

## What changed

| Area | Current decision |
| --- | --- |
| Farsi / Dari | Prefer female Persian Edge (Dilara); retain bundled Persian Piper when online speech fails. Dari remains a pronunciation approximation. |
| Kurmanji | Recovered Turkish Edge voices before the basic robotic voice. Google Turkish supplies an independent online pronunciation reserve. |
| Sindhi | The reference had no dedicated Sindhi override. Urdu Edge/Google are labelled approximations ahead of basic Sindhi. They are not native Sindhi engines. |
| Tigrinya / Sorani / Oromo | Preserve working local neural voices; recover the webapp's Amharic, Iraqi Arabic/Persian and Somali/Swahili pronunciation reserves respectively. |
| Pashto | Keep the exact female Edge voice and add its exact male voice; Persian pronunciation is a labelled last online approximation. These all depend on Edge availability. |
| Playback | Wait for Windows playback completion; no estimated-duration cutoff. Stop/cancel still interrupts playback and releases private audio. |
| Safe Speech | Default-on local masking of known profanity/slurs in displayed translations and spoken input. Off restores original text. Neutral medical/safeguarding terminology remains; originals and exports are not rewritten. |

Translation and dictation engines are unchanged. Explicit Offline/Basic voice settings never upload text. The existing layout is preserved except the requested joined controls.

## Evidence and limits

[Individual voice trials](voice-hotfix-live.json) use real synthesis/decoding on short synthetic common-use passages. [Automatic routing/outage trials](voice-hotfix-workflow.json) exercise actual providers, with only physical playback intercepted. One supplied Oromo phrase contains a letter outside the local model's accepted alphabet; the whole passage correctly moves to a pronunciation reserve.

All eight final automatic sample workflows completed. Farsi and Dari selected female Persian Edge; Kurmanji selected Turkish Emel; Sindhi selected Urdu Uzma. Seven survived the injected primary-route failure; Pashto did not survive a failure applied to every underlying Edge call. Its two exact voices are useful alternatives but not independent services. An earlier individual Farsi request timed out, so the local reserve remains necessary. Provider variability remains.

Regression checks cover reversible masking, unchanged saved originals, neutral clinical terms, obfuscation, explicit local-only routing, delayed-device playback and cancellation cleanup. Source/frozen reports accompany this package. A rendered native UI screenshot verifies the joined controls fit the existing layout.

Actual Windows silent-PCM playback completed a 0.4-second buffer in 0.453 seconds; cancellation requested after 0.15 seconds stopped a two-second buffer in 0.157 seconds. The synchronous PlaySound approach was rejected after a real-device test showed delayed cancellation. The final implementation uses the driver's [WHDR_DONE completion flag](https://learn.microsoft.com/en-us/windows/win32/multimedia/managing-data-blocks-by-polling) and resets its own output handle for cancellation. [Native playback check](playback-native-1.3.2.json).

Audio completion is not pronunciation certification. Turkish-for-Kurmanji and Urdu-for-Sindhi may sound more natural while mispronouncing language-specific words. The reference's local filter has finite multilingual term lists; it is not universal 18+ classification. No new model-quality claims or native-listener scores are made.

## Distribution

Use the single **GrayFeather-1.3.2-Windows-x64.zip**. All voices, runtime libraries, models, notices and existing corresponding source bundles are inside. Check the packaging JSON for archive size. A complete ZIP exceeding 2 GiB cannot be attached as one GitHub release asset; the single-file download must then be hosted elsewhere. No remote publication is performed here.

Parham (Leon) Faraji · leon-executes · PolyForm Noncommercial 1.0.0 for original application code. Third-party licences remain in force.
