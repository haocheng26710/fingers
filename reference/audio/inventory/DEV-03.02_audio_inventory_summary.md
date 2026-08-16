# Audio inventory summary

- Inventory: `reference/audio/inventory/DEV-03.01_audio_inventory.json`
- Inventory SHA256: `8a68d714a86fa8228e17b7f751da8060c558f79f881fb55994e5130caf199de2`
- Captured at: `2026-08-16T16:49:47.574426+00:00`
- Capture context: `reference/audio/inventory/DEV-03.02_inventory_capture_context.json`
- Capture context SHA256: `10472424e35958bc6cef156fe8b48c9b927f13b041414b2125b53dbec7d5e67c`
- Inventory role: `development_host_baseline_without_experimental_hardware`
- Experimental input hardware connected: `false`
- Experimental output hardware connected: `false`
- Experimental fixture connected: `false`
- Device binding: `deferred_until_hardware_connection`

> The experimental input, output and fixture were not connected during this capture. Existing endpoints are not experimental hardware and must not be bound.

## Host APIs

| Index | Name | Device count | Default input | Default output |
|---:|---|---:|---:|---:|
| 0 | MME | 5 | 1 | 3 |
| 1 | Windows DirectSound | 5 | 5 | 7 |
| 2 | Windows WASAPI | 3 | 12 | 11 |
| 3 | Windows WDM-KS | 11 | 20 | 13 |

## Devices

Device names below come directly from the verified inventory model.

| Index | Host API | Device name | Input channels | Output channels |
|---:|---|---|---:|---:|
| 0 | MME | Microsoft 声音映射器 - Input | 2 | 0 |
| 1 | MME | 阵列麦克风 (AMD Audio Device) | 2 | 0 |
| 2 | MME | Microsoft 声音映射器 - Output | 0 | 2 |
| 3 | MME | 耳机 (Senary Audio) | 0 | 6 |
| 4 | MME | 扬声器 (Senary Audio) | 0 | 6 |
| 5 | Windows DirectSound | 主声音捕获驱动程序 | 2 | 0 |
| 6 | Windows DirectSound | 阵列麦克风 (AMD Audio Device) | 2 | 0 |
| 7 | Windows DirectSound | 主声音驱动程序 | 0 | 2 |
| 8 | Windows DirectSound | 耳机 (Senary Audio) | 0 | 6 |
| 9 | Windows DirectSound | 扬声器 (Senary Audio) | 0 | 6 |
| 10 | Windows WASAPI | 扬声器 (Senary Audio) | 0 | 2 |
| 11 | Windows WASAPI | 耳机 (Senary Audio) | 0 | 2 |
| 12 | Windows WASAPI | 阵列麦克风 (AMD Audio Device) | 2 | 0 |
| 13 | Windows WDM-KS | Output 1 (Senary Audio headphone) | 0 | 2 |
| 14 | Windows WDM-KS | Output 2 (Senary Audio headphone) | 0 | 6 |
| 15 | Windows WDM-KS | Input (Senary Audio headphone) | 2 | 0 |
| 16 | Windows WDM-KS | Output 1 (Senary Audio output) | 0 | 2 |
| 17 | Windows WDM-KS | Output 2 (Senary Audio output) | 0 | 6 |
| 18 | Windows WDM-KS | Input (Senary Audio output) | 2 | 0 |
| 19 | Windows WDM-KS | 麦克风 (Senary Audio capture) | 2 | 0 |
| 20 | Windows WDM-KS | 阵列麦克风 (AMDAfdInstall Wave Microphone - 0) | 2 | 0 |
| 21 | Windows WDM-KS | 耳机 (@System32\\drivers\\bthhfenum.sys,#2;%1 Hands-Free%0<br>;([REDACTED_USER_DEFINED_DEVICE_NAME])) | 0 | 1 |
| 22 | Windows WDM-KS | 耳机 (@System32\\drivers\\bthhfenum.sys,#2;%1 Hands-Free%0<br>;([REDACTED_USER_DEFINED_DEVICE_NAME])) | 1 | 0 |
| 23 | Windows WDM-KS | 耳机 () | 0 | 2 |

`NO_AUDIO_PLAYBACK_OR_RECORDING_PERFORMED`
