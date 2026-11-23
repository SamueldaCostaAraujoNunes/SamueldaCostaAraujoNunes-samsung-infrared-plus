# Protocolo do ar Samsung ("02 92")

Mapa levantado a partir de 27 capturas de um controle Samsung real (23/11/2026), em `tests/fixtures/captures.json`.

Base: `SamsungAC0292Command` (infrared-protocols 10.7.0) e IRremoteESP8266 (`SAMSUNG_AC`).
Tempos: cabeçalho 690/-17844, seção 3086/-8864, bit 586 + -436 (0) / -1432 (1), LSB primeiro,
-2886 entre seções. Checksum de cada seção confere em 27/27 capturas.

## Quadros
| Tamanho | Quando | Seções |
|---|---|---|
| 14 bytes | toda tecla comum | S1 + ESTADO |
| 21 bytes | ligar / desligar | S1 + S2 (`01 D2 0F 00 00 00 00`) + ESTADO |

S1 = `02 92 0F 00 00 00 F0` (ligado) / `02 B2 0F 00 00 00 C0` (desligar).

## Seção ESTADO (7 bytes, índices 0–6)
| Byte | Bits | Campo | Valores observados |
|---|---|---|---|
| 0 | — | fixo | `01` |
| 1 | 0–3 | fixo | `2` |
| 1 | 4–7 + byte 2 bits 0–3 | checksum | |
| 2 | 4–7 | swing | `F` desligado, `A` vertical, `B` horizontal (`C` = ambos, segundo IRremoteESP8266, não capturado) |
| 3 | 1–3 | fan especial | `000` normal, `011` Fast, `101` WindFree |
| 3 | 4 | display (IRremoteESP8266) | sempre 1 |
| 3 | demais | fixo | `0x71` sem fan especial |
| 4 | 4–7 | temperatura − 16 | 16..30 |
| 5 | 0 | fixo | 1 |
| 5 | 1–3 | ventilador | 0 auto, 2 baixo, 4 médio, 5 alto, 7 turbo |
| 5 | 4–6 | modo | 0 auto, 1 frio, 2 desumidificar, 3 ventilar, 4 quente |
| 5 | 7 | ? | 1 no modo auto (no controle), 0 nos demais |
| 6 | 4–7 | power | `F` ligado, `C` desligado |

Fast = fan especial 011 + ventilador 7. WindFree = fan especial 101 + ventilador 0.

## Por que não usar o decodificador do core

`SamsungAC0292Command.from_raw_timings` (infrared-protocols 10.7.0) rejeita todas as capturas deste controle:
1. Quadros de 14 bytes: o core só aceita 21.
2. Cabeçalho chega separado do resto (receptor divide no espaço de 17,8 ms): o core exige o cabeçalho.
3. Modo auto do controle = `0x81` (bit 7 = 1, ventilador 0); o core espera `0x0D` (ventilador 6).
4. Swing horizontal (`B`), ventilador turbo (7), Fast e WindFree (byte 3 ≠ 0x71): fora do que o core aceita.
5. Desligar: o byte 5 traz o modo atual (`01` em auto); o core só reconhece o quadro fixo dele (`11`).
