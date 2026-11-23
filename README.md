# Samsung Infrared Plus

Integração personalizada do Home Assistant para controlar TVs e ar-condicionados Samsung por infravermelho, a partir de um proxy IR como um dispositivo ESPHome com `ir_rf_proxy`.

É uma cópia da integração oficial **Samsung Infrared** (`samsung_infrared`) com um domínio próprio (`samsung_infrared_plus`), então as duas podem ficar instaladas ao mesmo tempo. A diferença está no ar-condicionado:

| | `samsung_infrared` (core) | `samsung_infrared_plus` |
|---|---|---|
| Receptor IR (acompanha o controle original) | — | ✓ |
| Swing vertical | só desligado | ligado/desligado |
| Swing horizontal | — | ligado/desligado |
| Ventilador | auto, baixo, médio, alto | + turbo |
| Fast e WindFree | — | como *preset* |

A TV (botões e `media_player`) é a mesma do core.

## Requisitos

- Home Assistant 2026.10 ou mais recente (plataforma `infrared` com receptor).
- Um transmissor infravermelho configurado no Home Assistant. Para seguir o controle original, também um receptor.

### Receptor no ESPHome

O quadro do ar Samsung é longo (até ~350 transições) e começa com um espaço de ~17,8 ms. Os padrões do `remote_receiver` no ESP8266 cortam esse sinal, então ajuste:

```yaml
remote_receiver:
  pin:
    number: GPIO5
    inverted: true
  idle: 25ms        # maior que o espaço de 17,8 ms do cabeçalho
  buffer_size: 2kb  # o padrão de 1kb no ESP8266 não comporta o quadro de 21 bytes
  tolerance: 25%
```

Mesmo que o receptor entregue o cabeçalho separado do resto, a integração decodifica o quadro.

## Instalação

1. No HACS, abra **⋮ → Repositórios personalizados** e adicione `https://github.com/SamueldaCostaAraujoNunes/samsung-infrared-plus` como **Integração**.
2. Instale **Samsung Infrared Plus** e reinicie o Home Assistant.
3. Em **Configurações → Dispositivos e serviços → Adicionar integração**, escolha **Samsung Infrared Plus**.
4. Escolha **Ar-condicionado**, o transmissor e, se quiser, o receptor.

O receptor pode ser trocado ou removido depois em **Reconfigurar**.

## Ar-condicionado

| Recurso | Valores |
|---|---|
| Modo | desligado, automático, frio, quente, desumidificar, ventilar |
| Temperatura | 16 a 30 °C, de 1 em 1 |
| Ventilador | auto, baixo, médio, alto, turbo |
| Swing vertical / horizontal | ligado, desligado |
| Preset | nenhum, Fast, WindFree |

Como no controle original:
- Fast força o ventilador em turbo e WindFree força o automático; escolher um ventilador sai do preset.
- No modo automático o ventilador vai sempre como automático.
- Com o ar desligado, mudar temperatura, ventilador ou swing só fica registrado e vai junto no próximo "ligar".

**Com receptor**, cada tecla do controle original atualiza a entidade (o controle sempre manda o estado completo). O sinal de desligar só muda a energia.

O estado continua sendo presumido (`assumed_state`): o ar não informa nada de volta, então mudanças que não passam pelo Home Assistant nem pelo receptor não aparecem.

### Ainda não verificado

- Swing vertical e horizontal ligados juntos: usa o valor `C` documentado pelo IRremoteESP8266, que não foi capturado do controle.
- A integração sempre envia o quadro longo (21 bytes), como a do core. O controle manda 14 bytes nas teclas comuns.

## Protocolo

O mapa byte a byte, levantado a partir de capturas de um controle real, está em [docs/PROTOCOLO.md](docs/PROTOCOLO.md). O codificador/decodificador fica em `custom_components/samsung_infrared_plus/protocol.py`, sem dependência do Home Assistant.

Os testes recodificam as 27 capturas reais e conferem bit a bit:

```bash
pip install pytest
pytest tests
# ou, sem pytest:
python tests/test_protocol.py
```

Para ver os quadros recebidos, ative o log de depuração:

```yaml
logger:
  logs:
    custom_components.samsung_infrared_plus: debug
```

## Créditos e licença

Baseado na integração `samsung_infrared` do [Home Assistant](https://github.com/home-assistant/core) e na biblioteca [infrared-protocols](https://github.com/home-assistant-libs/infrared-protocols). Layout do protocolo conferido com o [IRremoteESP8266](https://github.com/crankyoldgit/IRremoteESP8266).

Licença Apache 2.0. Veja [LICENSE](LICENSE) e [NOTICE](NOTICE).
