Updated BOM Note – Part Replacement

## Summary

The circuit does not need a MOSFET because the op‑amp supplies a constant low‑voltage current. Replacing the discontinued IRL540 with a simple bipolar transistor works fine – the 2SD972 has been tested successfully

## ⚠️ Important Warnings

| Issue |	Recommendation |
| - |	- |
| IRL540 discontinued	| Do not try to source it; it’s no longer manufactured. |
| PCBWay’s suggested substitute – IRFZ44NPBF	| DO NOT USE. In a low‑voltage gate‑drive configuration the IRFZ44N will not turn on properly, resulting in little or no current flow. |

## Recommended Replacement Options

| Part	|	Type	|	Why it fits	|
| -	|	-	|	- |
| 2SD972	|	NPN bipolar transistor |	Proven to work in this design; handles the required current with the op‑amp’s low‑voltage output. |
|IRLZ44N (logic‑level MOSFET)	|	MOSFET	|	Suitable when you do need a MOSFET driven directly from 3.3 V/5 V microcontrollers (e.g., Arduino, ESP32). It turns fully on at low gate voltages, unlike the standard IRFZ44N which requires ~10 V. |

- Tip: If you ever need a MOSFET for a higher‑voltage gate‑drive application, choose a true logic‑level device (e.g., IRLZ44N) rather than a standard‑level part.
- Tip: For direct use with 3.3V/5V microcontrollers (like Arduino), the IRLZ44N (logic-level) is a better, more efficient choice than the standard IRFZ44N. The primary difference is that the IRLZ44N is a logic-level MOSFET, meaning it can be fully controlled by low-voltage logic (like a 3.3V or 5V microcontroller I/O pin, e.g esp32 chip), while the IRFZ44N is a standard-level MOSFET that requires a higher gate voltage (typically 10V) for full turn-on. 

## Further Reading

Reddit discussion – a community‑curated list of additional MOSFET/ transistor alternatives (link here [Reddit post](https://www.reddit.com/r/AskElectronics/comments/q2pisu/irl_vs_irf_mosfet_can_i_use_an_irf_mosfet_for/#:~:text=IRF3708:%20Rds(on)%20is,thus%20standard%2Dlevel.) for more alternatives. )
