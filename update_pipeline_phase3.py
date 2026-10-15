import os

file_path = r'c:\Users\roberto.navarro\Documents\paula\03_codigo_python\ejecutar_pipeline_unificado.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Size plotting (add std deviation shading)
old_talla_plot = '''            # Talla
            for m in MODELOS_CMIP6:
                if m in r["prediccion"][anio]:
                    ax_talla.plot(meses_x, r["prediccion"][anio][m]["talla"], 
                                 '-', linewidth=2, label=m)
            ax_talla.set_title(f'{morfo} — Projected size', fontweight='bold')'''
new_talla_plot = '''            # Talla
            for m in MODELOS_CMIP6:
                if m in r["prediccion"][anio]:
                    y_talla = r["prediccion"][anio][m]["talla"]
                    y_talla_std = r["prediccion"][anio][m]["talla_std"]
                    line_t = ax_talla.plot(meses_x, y_talla, '-', linewidth=2, label=m)
                    ax_talla.fill_between(meses_x, y_talla - y_talla_std, y_talla + y_talla_std,
                                         color=line_t[0].get_color(), alpha=0.2)
            ax_talla.set_title(f'{morfo} — Projected size (± SD)', fontweight='bold')'''
content = content.replace(old_talla_plot, new_talla_plot)

# Abundance plotting (limit lower bound to 0)
old_abund_plot = '''                    line = ax_abund.plot(meses_x, y_abund, '-', linewidth=2, label=m)
                    ax_abund.fill_between(meses_x, y_abund - y_std, y_abund + y_std,
                                         color=line[0].get_color(), alpha=0.2)'''
new_abund_plot = '''                    line = ax_abund.plot(meses_x, y_abund, '-', linewidth=2, label=m)
                    ax_abund.fill_between(meses_x, np.maximum(0, y_abund - y_std), y_abund + y_std,
                                         color=line[0].get_color(), alpha=0.2)'''
content = content.replace(old_abund_plot, new_abund_plot)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Phase 3 replacements done.")
