# Waterjet Cutting Speed Reference

Reference table for OMAX waterjet cutting speeds assuming a **50HP pump at 60,000 PSI** with standard abrasive (80 mesh garnet).

## Machinability Index

Relative cutting speed compared to mild steel (baseline = 1.0). Higher values cut faster.

| Material | Index | Notes |
|----------|-------|-------|
| Mild Steel | 1.0 | Baseline reference |
| Stainless Steel | 0.9 | 10% slower than mild steel |
| Aluminum | 2.9 | ~3x faster than mild steel |
| Titanium | 1.1 | Slightly faster than steel |
| Copper | 1.8 | |
| Brass | 2.0 | |
| Carbon Fiber | 4.0-5.0 | Varies by layup |
| Glass | 6.0+ | Very fast |
| Rubber | 15-25+ | Pure waterjet (no abrasive), very fast |

## Cutting Speeds (IPM) at Q3 Quality

Speeds in inches per minute for medium (Q3) edge quality.

| Thickness | Mild Steel | Stainless | Aluminum | Titanium | Brass | Rubber* |
|-----------|------------|-----------|----------|----------|-------|---------|
| 1/8" (0.125") | 18-22 | 16-20 | 50-60 | 18-24 | 35-40 | 300-500 |
| 1/4" (0.25") | 10-14 | 9-12 | 30-40 | 11-15 | 20-25 | 200-350 |
| 3/8" (0.375") | 7-10 | 6-9 | 22-28 | 8-11 | 14-18 | 150-250 |
| 1/2" (0.5") | 5-7 | 4.5-6 | 15-20 | 6-8 | 10-14 | 100-180 |
| 3/4" (0.75") | 3-4.5 | 2.5-4 | 9-12 | 3.5-5 | 6-9 | 60-120 |
| 1" (1.0") | 2-3 | 1.8-2.7 | 6-9 | 2.5-3.5 | 4-6 | 40-80 |
| 1.5" (1.5") | 1-1.5 | 0.9-1.4 | 3-5 | 1.2-1.8 | 2-3.5 | 20-50 |
| 2" (2.0") | 0.5-1.0 | 0.4-0.9 | 1.5-3 | 0.6-1.1 | 1-2 | 10-30 |

*\*Rubber speeds are for pure waterjet (no abrasive) at ~30,000-40,000 PSI. Speeds vary significantly based on durometer (hardness).*

## Quality vs Speed Multipliers

Edge quality settings affect cutting speed significantly.

| Quality | Finish | Speed Multiplier | Use Case |
|---------|--------|------------------|----------|
| Q1 | Rough | 3-6x faster | Separation cuts, will be machined |
| Q2 | Moderate | 2-3x faster | Non-critical edges |
| Q3 | Medium | 1x (baseline) | General purpose |
| Q4 | Smooth | 0.5-0.7x | Visible edges |
| Q5 | Very smooth | 0.3-0.5x | Precision/finished parts |

## Factors Affecting Speed

### Equipment Variables
- **Nozzle/orifice size**: Larger = faster (0.014" nozzle cuts ~2.5x faster than 0.010")
- **Pressure**: 90ksi systems cut 30-50% faster than 60ksi
- **Abrasive flow rate**: Higher flow = faster cut
- **Pump type**: OMAX direct drive pumps are ~33% more efficient than intensifier pumps at same HP

### Material Variables
- **Hardness**: Harder materials generally cut slower (exception: titanium cuts faster than steel)
- **Thickness**: Relationship is exponential - doubling thickness more than halves speed
- **Brittleness**: Glass, ceramics, stone may need adjusted machinability values

## Pure Waterjet vs Abrasive Waterjet

| Type | Pressure | Materials | Notes |
|------|----------|-----------|-------|
| Pure Waterjet | 30,000-40,000 PSI | Rubber, foam, gaskets, leather, textiles, food | No abrasive, lower kerf, cleaner edge |
| Abrasive Waterjet | 60,000-90,000 PSI | Metals, stone, glass, composites, ceramics | Uses 80 mesh garnet, wider kerf |

**Rubber cutting notes:**
- Pure waterjet preferred - no abrasive contamination
- Can stack multiple sheets (up to 8") and cut simultaneously
- Lower pressure reduces material deformation
- Speeds vary by durometer (Shore A hardness) - softer rubber cuts faster

## Online Calculators

For precise values with your specific configuration:
- [Hypertherm Waterjet Calculator](https://waterjet-calculator.hypertherm.com/)
- [KMT Cut Calculator](https://kmtwaterjet.com/sales-service/kmt-waterjet-cut-calculator/)
- OMAX IntelliMAX software (built-in for 60+ materials)

## Sources

- [OMAX Factors of Speed](https://www.omax.com/en/us/media-center/tips/factors-speed)
- [TechniWaterjet Speed Guide](https://www.techniwaterjet.com/waterjet-cutting-speed/)
- [TechniWaterjet Rubber Cutting](https://www.techniwaterjet.com/waterjet-rubber-cutting/)
- [VICHOR Waterjet Cutting Speed](https://www.vichor.com/waterjet-cutting-machines/waterjet-cutting-speed-explained-what-you-need-to-know/)
- [Practical Machinist Forum](https://www.practicalmachinist.com/)

---

*Note: These are estimates based on published data and machinability ratios. Actual speeds depend on specific nozzle configuration, material batch variations, and machine condition.*
