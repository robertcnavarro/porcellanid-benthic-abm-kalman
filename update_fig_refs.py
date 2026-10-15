import os

docx_file = 'build_q1_docx.py'
with open(docx_file, 'r', encoding='utf-8') as f:
    docx = f.read()

replacements = {
    "'Fig1_Series_Temporales_Campo.png'": "'Fig1_Field_Time_Series.png'",
    "'Fig2_Distribucion_Tallas_Sexo.png'": "'Fig2_Size_Sex_Distribution.png'",
    "'Fig3_Validacion_Kalman_Talla.png'": "'Fig3_Kalman_Validation_Size.png'",
    "'Fig4_Validacion_IBM_Abundancia.png'": "'Fig4_IBM_Validation_Abundance.png'",
    "'Fig5_Comparacion_Metodos_LOMO.png'": "'Fig5_Method_Comparison_LOMO.png'",
    "'Fig6_Proyeccion_CMIP6_2026.png'": "'Fig6_CMIP6_Projection_2026.png'",
    "'Fig6_Proyeccion_CMIP6_2027.png'": "'Fig7_CMIP6_Projection_2027.png'",
    '("Bayes")': '("Bayes")' # Just dummy to ensure we don't need it
}

# The user wants me to also ensure the caption in Fig 5 explicitly mentions "Mecánico" (Mechanistic) if not already clear.
# It says: '"Mecánico" represents the mechanistic ABM' which is already good English bridging for the Spanish plot. Let's make it slightly clearer:
old_fig5_caption = '"Mecánico" represents the mechanistic ABM'
new_fig5_caption = '"Mecánico" (Mechanistic) represents the deterministic ABM'
docx = docx.replace(old_fig5_caption, new_fig5_caption)

for old, new in replacements.items():
    docx = docx.replace(old, new)
    
# Save to file
with open(docx_file, 'w', encoding='utf-8') as f:
    f.write(docx)

print("Figure references updated successfully.")
