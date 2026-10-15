import os
import re

file_path = r'c:\Users\roberto.navarro\Documents\paula\03_codigo_python\ejecutar_pipeline_unificado.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update g_crecimiento to include von Bertalanffy limit
old_g_crecimiento = '''def g_crecimiento(T, a, T_opt, sigma):
    return a * np.exp(-0.5 * ((T - T_opt) / sigma) ** 2)

class KalmanTalla:
    def __init__(self, x0, P0, theta):
        self.x, self.P = x0, P0
        self.a, self.T_opt, self.sigma, self.Q = theta
    def predecir(self, T_k):
        self.x = self.x + g_crecimiento(T_k, self.a, self.T_opt, self.sigma)'''

new_g_crecimiento = '''def g_crecimiento(T, a, T_opt, sigma, x_actual, L_inf):
    incremento = a * np.exp(-0.5 * ((T - T_opt) / sigma) ** 2)
    # Von Bertalanffy effect: growth slows down as it approaches L_inf
    return incremento * max(0.0, (L_inf - x_actual) / L_inf)

class KalmanTalla:
    def __init__(self, x0, P0, theta, L_inf):
        self.x, self.P = x0, P0
        self.a, self.T_opt, self.sigma, self.Q = theta
        self.L_inf = L_inf
    def predecir(self, T_k):
        self.x = self.x + g_crecimiento(T_k, self.a, self.T_opt, self.sigma, self.x, self.L_inf)'''
content = content.replace(old_g_crecimiento, new_g_crecimiento)

# 2. Update correr_filtro to accept L_inf
content = content.replace(
    'def correr_filtro(temperaturas, observaciones, R_obs, x0, P0, theta, pasos_con_actualizacion=None):',
    'def correr_filtro(temperaturas, observaciones, R_obs, x0, P0, theta, L_inf, pasos_con_actualizacion=None):'
)
content = content.replace('kf = KalmanTalla(x0, P0, theta)', 'kf = KalmanTalla(x0, P0, theta, L_inf)')

# 3. Update _neg_log_vero
content = content.replace(
    'def _neg_log_vero(theta, T, obs, R, x0, P0):',
    'def _neg_log_vero(theta, T, obs, R, x0, P0, L_inf):'
)
content = content.replace(
    '_,_,_,_, innov, S = correr_filtro(T, obs, R, x0, P0, theta)',
    '_,_,_,_, innov, S = correr_filtro(T, obs, R, x0, P0, theta, L_inf)'
)

# 4. Update ajustar_mle_kalman and bounds
content = content.replace(
    'def ajustar_mle_kalman(T, obs, R, x0, P0, theta0=(0.8,27.5,2.0,0.15)):',
    'def ajustar_mle_kalman(T, obs, R, x0, P0, L_inf, theta0=(0.8,27.5,2.0,0.15)):'
)
old_bounds = 'bounds = [(0.0,5.0),(20.0,35.0),(0.3,10.0),(1e-4,5.0)]'
new_bounds = 'bounds = [(0.01, 1.5), (20.0, 35.0), (0.5, 10.0), (1e-4, 5.0)]'
content = content.replace(old_bounds, new_bounds)
content = content.replace(
    'return minimize(_neg_log_vero, theta0, args=(T,obs,R,x0,P0), method="L-BFGS-B", bounds=bounds)',
    'return minimize(_neg_log_vero, theta0, args=(T,obs,R,x0,P0, L_inf), method="L-BFGS-B", bounds=bounds)'
)

# 5. Update validacion_lomo_kalman
content = content.replace(
    'def validacion_lomo_kalman(T, obs, R, x0, P0, theta0=(0.8,27.5,2.0,0.15)):',
    'def validacion_lomo_kalman(T, obs, R, x0, P0, L_inf, theta0=(0.8,27.5,2.0,0.15)):'
)
content = content.replace(
    'res = ajustar_mle_kalman(T, obs_k, R_k, x0, P0, theta0)',
    'res = ajustar_mle_kalman(T, obs_k, R_k, x0, P0, L_inf, theta0)'
)
content = content.replace(
    '_,_, x_pred, P_pred, _, _ = correr_filtro(T, obs, R, x0, P0, res.x, mascara)',
    '_,_, x_pred, P_pred, _, _ = correr_filtro(T, obs, R, x0, P0, res.x, L_inf, mascara)'
)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Phase 1 replacements done.")
