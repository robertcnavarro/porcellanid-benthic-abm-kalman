import os

file_path = r'c:\Users\roberto.navarro\Documents\paula\03_codigo_python\ejecutar_pipeline_unificado.py'

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

replacements = {
    "'Fig1_Series_Temporales_Campo.png'": "'Fig1_Field_Time_Series.png'",
    "'Fig2_Distribucion_Tallas_Sexo.png'": "'Fig2_Size_Sex_Distribution.png'",
    "'Fig3_Validacion_Kalman_Talla.png'": "'Fig3_Kalman_Validation_Size.png'",
    "'Fig4_Validacion_IBM_Abundancia.png'": "'Fig4_IBM_Validation_Abundance.png'",
    "'Fig5_Comparacion_Metodos_LOMO.png'": "'Fig5_Method_Comparison_LOMO.png'",
    "f'Fig6_Proyeccion_CMIP6_{anio}.png'": "f'Fig6_CMIP6_Projection_{anio}.png' if anio == 2026 else f'Fig7_CMIP6_Projection_{anio}.png'"
}

for old, new in replacements.items():
    content = content.replace(old, new)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Updated file successfully")
