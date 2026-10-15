import os

docx_file = 'build_q1_docx.py'
with open(docx_file, 'r', encoding='utf-8') as f:
    docx = f.read()

# 1. Update the add_eq function to handle numbering
old_add_eq = '''    def add_eq(text):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(text)
        r.italic = True'''

new_add_eq = '''    eq_counter = [1]
    def add_eq(text):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        # Format the equation and the number
        r = p.add_run(text)
        r.italic = True
        r.font.name = 'Cambria Math'
        
        r_num = p.add_run(f"      ({eq_counter[0]})")
        r_num.italic = False
        r_num.bold = False
        eq_counter[0] += 1'''
docx = docx.replace(old_add_eq, new_add_eq)

# 2. Update the equations text
docx = docx.replace('add_eq("dN/dt = -μ * N(t)")', 'add_eq("dN/dt = -μ N(t)")')
docx = docx.replace('add_eq("Nh = a * CW^b")', 'add_eq("N_h = a CW^b")')
docx = docx.replace('add_eq("K(Tt) = K_ref * exp( -(Tt - T_opt)² / (2 * σ_T,g²) )")', 'add_eq("K(T_t) = K_ref exp[-(T_t - T_opt)² / (2σ_T,g²)]")')
docx = docx.replace('add_eq("CW_i(t+Δt) = CW_i(t) + (L_∞ - CW_i(t)) * (1 - exp(-K(Tt) * Δt/365))")', 'add_eq("CW_i(t+Δt) = CW_i(t) + (L_∞ - CW_i(t))[1 - exp(-K(T_t) Δt / 365)]")')
docx = docx.replace('add_eq("N_recruits ~ Poisson( R_ext(St, Tt, Nt) )")', 'add_eq("N_recruits ~ Poisson( R_ext(S_t, T_t, N_t) )")')
docx = docx.replace('add_eq("R_ext = R0_max * exp( -0.5 * (((St - S_opt)/σ_S)² + ((Tt - T_opt)/σ_T)²) ) * max(0, 1 - Nt / K_basket)")', 'add_eq("R_ext = R0_max exp(-0.5[((S_t - S_opt)/σ_S)² + ((T_t - T_opt)/σ_T)²]) max(0, 1 - N_t / K_basket)")')
docx = docx.replace('add_eq("μ_i(Tt) = μ_base + γ_thermal / (1 + exp(-(Tt - T_crit)/0.5))")', 'add_eq("μ_i(T_t) = μ_base + γ_thermal / [1 + exp(-(T_t - T_crit)/0.5)]")')
docx = docx.replace('add_eq("x_k = x_{k-1} + g(T_k) + w_k,   w_k ~ N(0, Q)")', 'add_eq("x_k = x_{k-1} + g(T_k) + w_k,   w_k ~ N(0, Q)")') # I will replace this with cleaner text
docx = docx.replace('add_eq("x_k = x_{k-1} + g(T_k) + w_k,   w_k ~ N(0, Q)")', 'add_eq("x_k = x_k-1 + g(T_k) + w_k,   w_k ~ N(0, Q)")')
docx = docx.replace('add_eq("z_k = x_k + v_k,   v_k ~ N(0, R_k)")', 'add_eq("z_k = x_k + v_k,   v_k ~ N(0, R_k)")')

with open(docx_file, 'w', encoding='utf-8') as f:
    f.write(docx)

print("Equations formatted.")
