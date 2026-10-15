import os

file_path = r'c:\Users\roberto.navarro\Documents\paula\03_codigo_python\ejecutar_pipeline_unificado.py'

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

replacements = {
    "SST observada (Open-Meteo Archive)": "Observed SST (Open-Meteo Archive)",
    "Umbral estrÃ©s": "Stress threshold",
    "Umbral estrés": "Stress threshold",
    "'A) Condiciones ambientales durante el muestreo'": "'A) Environmental conditions during sampling'",
    "'Individuos / canasta'": "'Individuals / collector'",
    "'B) Abundancia por canasta colectora (4.0 dm³)'": "'B) Abundance per sampling collector (4.0 dm³)'",
    "'B) Abundancia por canasta colectora (4.0 dmÂ³)'": "'B) Abundance per sampling collector (4.0 dm³)'",
    "'Mes de muestreo'": "'Sampling month'",
    "'Ancho de caparazón (mm)'": "'Carapace width (mm)'",
    "'Ancho de caparazÃ³n (mm)'": "'Carapace width (mm)'",
    "'C) Ancho medio de caparazón por morfotipo'": "'C) Mean carapace width per morphotype'",
    "'C) Ancho medio de caparazÃ³n por morfotipo'": "'C) Mean carapace width per morphotype'",
    "'Distribución de tallas y proporción sexual por morfotipo'": "'Size distribution and sex ratio by morphotype'",
    "'DistribuciÃ³n de tallas y proporciÃ³n sexual por morfotipo'": "'Size distribution and sex ratio by morphotype'",
    "'Densidad'": "'Density'",
    "Media = ": "Mean = ",
    "Mediana = ": "Median = ",
    "'Validación del filtro de Kalman: ancho de caparazón (2009-2010)'": "'Kalman filter validation: carapace width (2009-2010)'",
    "'ValidaciÃ³n del filtro de Kalman: ancho de caparazÃ³n (2009-2010)'": "'Kalman filter validation: carapace width (2009-2010)'",
    "Observado (± DE)": "Observed (± SD)",
    "Observado (Â± DE)": "Observed (± SD)",
    "Kalman (filtrado)": "Kalman (filtered)",
    "'Validación del modelo individual-based: abundancia (2009-2010)'": "'Individual-based model validation: abundance (2009-2010)'",
    "'ValidaciÃ³n del modelo individual-based: abundancia (2009-2010)'": "'Individual-based model validation: abundance (2009-2010)'",
    "IBM (simulado)": "IBM (simulated)",
    "'Comparación de métodos: RMSE fuera de muestra (LOMO CV)'": "'Method comparison: out-of-sample RMSE (LOMO CV)'",
    "'ComparaciÃ³n de mÃ©todos: RMSE fuera de muestra (LOMO CV)'": "'Method comparison: out-of-sample RMSE (LOMO CV)'",
    "'RMSE Talla (mm)'": "'CW RMSE (mm)'",
    "'RMSE Talla'": "'CW RMSE'",
    "'RMSE Abundancia (individuos/canasta)'": "'Abundance RMSE (individuals/collector)'",
    "'RMSE Abundancia'": "'Abundance RMSE'",
    "Umbral (": "Threshold (",
    "'Proyección SST bajo CMIP6 - {anio}'": "'SST Projection under CMIP6 - {anio}'",
    "'ProyecciÃ³n SST bajo CMIP6 - {anio}'": "'SST Projection under CMIP6 - {anio}'",
    "f'{morfo} — Talla proyectada'": "f'{morfo} — Projected size'",
    "f'{morfo} â€” Talla proyectada'": "f'{morfo} — Projected size'",
    "'Ancho caparazón (mm)'": "'Carapace width (mm)'",
    "'Ancho caparazÃ³n (mm)'": "'Carapace width (mm)'",
    "f'{morfo} — Abundancia proyectada (± DE)'": "f'{morfo} — Projected abundance (± SD)'",
    "f'{morfo} â€” Abundancia proyectada (Â± DE)'": "f'{morfo} — Projected abundance (± SD)'",
    "set_xlabel('Mes'": "set_xlabel('Month'",
    "PIPELINE UNIFICADO EXECUTADO DE PRINCIPIO A FIN CON EXITO TOTAL": "UNIFIED PIPELINE EXECUTED FROM START TO FINISH WITH TOTAL SUCCESS",
    "PIPELINE UNIFICADO EXECUTADO DE PRINCIPIO A FIN CON Ã‰XITO TOTAL": "UNIFIED PIPELINE EXECUTED FROM START TO FINISH WITH TOTAL SUCCESS"
}

# Apply all replacements
for old, new in replacements.items():
    content = content.replace(old, new)
    
# Names of the methods in Fig 5
# nombres_metodos = ["Media Móvil", "Mecánico", "Bayes", "Random Forest"]
content = content.replace('"Media Móvil"', '"Moving Average"')
content = content.replace('"Media MÃ³vil"', '"Moving Average"')
content = content.replace('"Mecánico"', '"Mechanistic"')
content = content.replace('"MecÃ¡nico"', '"Mechanistic"')

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Translation of plot labels completed successfully.")
