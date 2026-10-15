import os

file_path = r'c:\Users\roberto.navarro\Documents\paula\03_codigo_python\ejecutar_pipeline_unificado.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# I need to get L_inf in the main loop. Let's do it right after `abm` is created.
old_abm_init = 'abm = ABM_DataDriven(datos[morfo], morfo=morfo, seed=42)'
new_abm_init = 'abm = ABM_DataDriven(datos[morfo], morfo=morfo, seed=42)\n    L_inf = abm.talla_max'
content = content.replace(old_abm_init, new_abm_init)

old_kalman_1 = 'lomo_kalman = validacion_lomo_kalman(T_campana, obs_talla, R_talla, x0_k, P0_k)'
new_kalman_1 = 'lomo_kalman = validacion_lomo_kalman(T_campana, obs_talla, R_talla, x0_k, P0_k, L_inf)'
content = content.replace(old_kalman_1, new_kalman_1)

old_kalman_2 = 'theta_kalman = ajustar_mle_kalman(T_campana, obs_talla, R_talla, x0_k, P0_k).x'
new_kalman_2 = 'theta_kalman = ajustar_mle_kalman(T_campana, obs_talla, R_talla, x0_k, P0_k, L_inf).x'
content = content.replace(old_kalman_2, new_kalman_2)

old_kalman_3 = 'x_filt,_,_,_,_,_ = correr_filtro(T_campana, obs_talla, R_talla, x0_k, P0_k, theta_kalman)'
new_kalman_3 = 'x_filt,_,_,_,_,_ = correr_filtro(T_campana, obs_talla, R_talla, x0_k, P0_k, theta_kalman, L_inf)'
content = content.replace(old_kalman_3, new_kalman_3)

old_kalman_pred = 'kf_fwd = KalmanTalla(x_filt[-1], 0.1, theta_kalman)'
new_kalman_pred = 'kf_fwd = KalmanTalla(x_filt[-1], 0.1, theta_kalman, L_inf)'
content = content.replace(old_kalman_pred, new_kalman_pred)

# Modify the CMIP6 projection loop to store std
old_talla_serie = '''talla_serie = []
            for T_k in T_arr:
                xk,_ = kf_fwd.predecir(T_k)
                talla_serie.append(xk)'''
new_talla_serie = '''talla_serie = []
            talla_std_serie = []
            for T_k in T_arr:
                xk, Pk = kf_fwd.predecir(T_k)
                talla_serie.append(xk)
                talla_std_serie.append(np.sqrt(Pk))'''
content = content.replace(old_talla_serie, new_talla_serie)

old_pred = '{"talla": np.array(talla_serie), "abundancia": sim_abund, "abundancia_std": sim_abund_std, "temps": T_arr}'
new_pred = '{"talla": np.array(talla_serie), "talla_std": np.array(talla_std_serie), "abundancia": sim_abund, "abundancia_std": sim_abund_std, "temps": T_arr}'
content = content.replace(old_pred, new_pred)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Phase 2 replacements done.")
