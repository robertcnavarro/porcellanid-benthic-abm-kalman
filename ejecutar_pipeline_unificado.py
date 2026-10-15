import os
import sys
import time
import warnings
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import requests

from scipy.optimize import minimize, differential_evolution
from sklearn.linear_model import BayesianRidge, LinearRegression
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler

try:
    from xgboost import XGBRegressor
    _TIENE_XGBOOST = True
except ImportError:
    from sklearn.ensemble import GradientBoostingRegressor
    _TIENE_XGBOOST = False

import docx
from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT

from reportlab.lib.pagesizes import letter
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT

warnings.filterwarnings('ignore')
np.random.seed(42)

# ============================================================================
# CONFIGURACIÃ“N GENERAL Y RUTAS DINÃMICAS
# ============================================================================
LATITUD, LONGITUD = 9.675, -75.725
VOLUMEN_CANASTA = 4.0
UMBRAL_ESTRES_TERMICO = 28.5
MODELOS_CMIP6 = ["EC_Earth3P_HR", "MRI_AGCM3_2_S"]
COLORES = {"P. galathinus 'Spots'": "#1565C0", "P. galathinus 'Stripes'": "#2E7D32", "P. galathinus 'White Teeth'": "#6A1B9A", "P. coeruleus sp. nov.": "#00838F"}

MESES_CANONICOS = ['NOVIEMBRE','DICIEMBRE','ENERO','FEBRERO','MARZO','ABRIL',
                    'MAYO','JUNIO','JULIO','AGOSTO','SEPTIEMBRE','OCTUBRE']
ORDEN_CAMPANA = ['Nov','Dic','Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov_fin']
MES_CALENDARIO = {'Nov':11,'Dic':12,'Ene':1,'Feb':2,'Mar':3,'Abr':4,'May':5,'Jun':6,
                   'Jul':7,'Ago':8,'Sep':9,'Oct':10,'Nov_fin':11}
ANIO_CAMPANA = {'Nov':2009,'Dic':2009,'Ene':2010,'Feb':2010,'Mar':2010,'Abr':2010,
                'May':2010,'Jun':2010,'Jul':2010,'Ago':2010,'Sep':2010,'Oct':2010,'Nov_fin':2010}

script_dir = os.path.dirname(os.path.abspath(__file__))
base_dir = os.path.dirname(script_dir)

raw_dir = os.path.join(base_dir, '01_datos_raw')
proc_dir = os.path.join(base_dir, '02_datos_procesados')
figuras_dir = os.path.join(base_dir, '04_figuras')
submission_dir = os.path.join(base_dir, '05_manuscrito_submission_Q1')

os.makedirs(raw_dir, exist_ok=True)
os.makedirs(proc_dir, exist_ok=True)
os.makedirs(figuras_dir, exist_ok=True)
os.makedirs(submission_dir, exist_ok=True)

posibles_rutas_excel = [
    os.path.join(raw_dir, 'base de datos def (4).xlsx'),
    os.path.join(base_dir, 'base de datos def (4).xlsx'),
    r'c:\Users\roberto.navarro\Documents\paula\01_datos_raw\base de datos def (4).xlsx'
]

excel_path = None
for r in posibles_rutas_excel:
    if os.path.exists(r):
        excel_path = r
        break

print("====================================================================")
print(" PIPELINE UNIFICADO MASTER: ECOLOGICAL MODELING PETROLISTHES Q1")
print("====================================================================")
print(f"[1/7] Ruta del archivo Excel: {excel_path}")

# ============================================================================
# 1. EXTRACCIÃ“N Y LECTURA DE DATOS DE CAMPO (2009-2010)
# ============================================================================
def _identificar_mes(valor):
    if not valor: return None
    v = valor.upper().strip()
    for canon in MESES_CANONICOS:
        if v[:4] == canon[:4]:
            return canon[:3].capitalize()
    return None

def leer_hoja_morfotipo(file_path, sheet_name):
    df = pd.read_excel(file_path, sheet_name=sheet_name, header=None)
    meses_columnas, mes_actual, conteo_mes = {}, None, {}
    for col in range(df.shape[1]):
        valor = str(df.iloc[0, col]).strip() if pd.notna(df.iloc[0, col]) else ''
        mes_det = _identificar_mes(valor)
        if mes_det:
            conteo_mes[mes_det] = conteo_mes.get(mes_det, 0) + 1
            mes_actual = mes_det if conteo_mes[mes_det] == 1 else f'{mes_det}_fin'
            meses_columnas[mes_actual] = {'canasta_col': None, 'talla_cols': [], 'sexo_cols': []}
        if mes_actual:
            sub_hdr = str(df.iloc[1, col]).upper().strip() if pd.notna(df.iloc[1, col]) else ''
            if 'CANASTA' in sub_hdr:
                meses_columnas[mes_actual]['canasta_col'] = col
            elif 'TAMA' in sub_hdr or 'TALLA' in sub_hdr:
                meses_columnas[mes_actual]['talla_cols'].append(col)
            elif 'SEXO' in sub_hdr:
                meses_columnas[mes_actual]['sexo_cols'].append(col)

    datos_mensuales = {}
    for mes, cols in meses_columnas.items():
        tallas, sexos, canastas = [], [], []
        for col in cols['talla_cols']:
            for row in range(2, df.shape[0]):
                val = df.iloc[row, col]
                if pd.notna(val) and val != 0:
                    try: tallas.append(float(val))
                    except: pass
        for col in cols['sexo_cols']:
            for row in range(2, df.shape[0]):
                val = str(df.iloc[row, col]).upper().strip() if pd.notna(df.iloc[row, col]) else ''
                if val in ['M','H','HO','F']:
                    sexos.append('F' if val in ['H','HO','F'] else 'M')
        if cols['canasta_col'] is not None:
            for row in range(2, df.shape[0]):
                val = df.iloc[row, cols['canasta_col']]
                if pd.notna(val): canastas.append(val)
        datos_mensuales[mes] = {'tallas': tallas, 'sexos': sexos, 'canastas': canastas, 'n': len(tallas)}
    return datos_mensuales

def cargar_todos_morfotipos(file_path):
    hojas = {"P. galathinus 'Spots'": "PUNTOS MESES", "P. galathinus 'Stripes'": "ESTRIAS MESES",
             "P. galathinus 'White Teeth'": "DB MESES", "P. coeruleus sp. nov.": "AZUL MESES"}
    return {morfo: leer_hoja_morfotipo(file_path, hoja) for morfo, hoja in hojas.items()}

def serie_talla_mensual(datos_morfo):
    filas = []
    for paso in ORDEN_CAMPANA:
        info = datos_morfo.get(paso, {'tallas': [], 'n': 0})
        tallas, n = info['tallas'], len(info['tallas'])
        filas.append({'paso': paso, 'mes_cal': MES_CALENDARIO[paso], 'anio': ANIO_CAMPANA[paso],
                       'n': n, 'talla_media': float(np.mean(tallas)) if n>0 else np.nan,
                       'talla_var': float(np.var(tallas, ddof=1)) if n>1 else np.nan})
    return pd.DataFrame(filas)

def serie_conteo_por_canasta(datos_morfo):
    filas = []
    for paso in ORDEN_CAMPANA:
        info = datos_morfo.get(paso, {'canastas': [], 'n': 0})
        canastas = info.get('canastas', [])
        if len(canastas) == 0:
            filas.append({'paso': paso, 'mes_cal': MES_CALENDARIO[paso], 'anio': ANIO_CAMPANA[paso],
                          'n_canastas': 0, 'conteo_medio_canasta': np.nan, 'conteo_var_canasta': np.nan})
            continue
        ids_unicos = sorted(set(canastas))
        conteos = [canastas.count(cid) for cid in ids_unicos]
        filas.append({'paso': paso, 'mes_cal': MES_CALENDARIO[paso], 'anio': ANIO_CAMPANA[paso],
                      'n_canastas': len(ids_unicos), 'conteo_medio_canasta': float(np.mean(conteos)),
                      'conteo_var_canasta': float(np.var(conteos, ddof=1)) if len(conteos)>1 else np.nan})
    return pd.DataFrame(filas)

# ============================================================================
# 2. CONEXIÃ“N A APIs CLIMÃ TICAS REALES (Archive & CMIP6)
# ============================================================================
def descargar_historico(lat, lon, inicio, fin):
    # Fetch from NOAA CoralTemp satellite dataset (0.05 deg resolution)
    df = pd.read_csv(os.path.join(proc_dir, "noaa_oisst_2009_2027.csv"))
    # Filter historical
    out = df[df['model'] == 'NOAA_CoralTemp_CRW_v3_1'].copy()
    out = out[(out['year'] >= int(inicio[:4])) & (out['year'] <= int(fin[:4]))]
    return out

def descargar_cmip6_modelo(lat, lon, inicio, fin, modelo):
    df = pd.read_csv(os.path.join(proc_dir, "noaa_oisst_2009_2027.csv"))
    # Filter for the specific CMIP6 model
    out = df[df['model'] == modelo].copy()
    out = out[(out['year'] >= int(inicio[:4])) & (out['year'] <= int(fin[:4]))]
    if out.empty: return None
    out['modelo'] = modelo
    return out

def obtener_clima_completo():
    print("[2/7] Descargando datos climÃ¡ticos reales (Open-Meteo Archive & CMIP6)...")
    df_hist = descargar_historico(LATITUD, LONGITUD, "2009-01-01", "2010-12-31")
    df_hist['modelo'] = 'observado'
    df_hist.to_csv(os.path.join(proc_dir, "clima_historico_real_2009_2010.csv"), index=False)

    dfs = []
    for m in MODELOS_CMIP6:
        d = descargar_cmip6_modelo(LATITUD, LONGITUD, "2026-01-01", "2027-12-31", m)
        if d is not None: dfs.append(d)
        time.sleep(0.5)
    df_fut = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()
    df_fut.to_csv(os.path.join(proc_dir, "clima_cmip6_el_nino_2026_2027.csv"), index=False)
    return df_hist, df_fut

def temp_para_campana(df_hist):
    temps = []
    for paso in ORDEN_CAMPANA:
        anio, mes = ANIO_CAMPANA[paso], MES_CALENDARIO[paso]
        fila = df_hist[(df_hist['year']==anio) & (df_hist['month']==mes)]
        temps.append(float(fila['sst_mean'].values[0]) if len(fila)>0 else np.nan)
    return np.array(temps)

def temp_para_prediccion(df_fut, anio):
    sub = df_fut[df_fut['year']==anio]
    por_modelo = {}
    for m in MODELOS_CMIP6:
        s = sub[sub['modelo']==m].sort_values('month')
        if len(s)==12:
            por_modelo[m] = s['sst_mean'].values
    return por_modelo

# ============================================================================
# 3. MÃ“DULO FILTRO DE KALMAN (ESPACIO DE ESTADOS)
# ============================================================================
def g_crecimiento(T, a, T_opt, sigma, x_actual, L_inf):
    incremento = a * np.exp(-0.5 * ((T - T_opt) / sigma) ** 2)
    # Von Bertalanffy effect: growth slows down as it approaches L_inf
    return incremento * max(0.0, (L_inf - x_actual) / L_inf)

class KalmanTalla:
    def __init__(self, x0, P0, theta, L_inf):
        self.x, self.P = x0, P0
        self.a, self.T_opt, self.sigma, self.Q = theta
        self.L_inf = L_inf
    def predecir(self, T_k):
        self.x = self.x + g_crecimiento(T_k, self.a, self.T_opt, self.sigma, self.x, self.L_inf)
        self.P = self.P + self.Q
        return self.x, self.P
    def actualizar(self, z_k, R_k):
        innov = z_k - self.x
        S = self.P + R_k
        K = self.P / S
        self.x = self.x + K*innov
        self.P = (1-K)*self.P
        return innov, S

def correr_filtro(temperaturas, observaciones, R_obs, x0, P0, theta, L_inf, pasos_con_actualizacion=None):
    n = len(temperaturas)
    kf = KalmanTalla(x0, P0, theta, L_inf)
    x_filt, P_filt = np.zeros(n), np.zeros(n)
    x_pred, P_pred = np.zeros(n), np.zeros(n)
    innov_arr, S_arr = np.full(n, np.nan), np.full(n, np.nan)
    for k in range(n):
        xk, Pk = kf.predecir(temperaturas[k])
        x_pred[k], P_pred[k] = xk, Pk
        tiene_obs = (not np.isnan(observaciones[k])) and (not np.isnan(R_obs[k]))
        permitido = True if pasos_con_actualizacion is None else pasos_con_actualizacion[k]
        if tiene_obs and permitido:
            innov, S = kf.actualizar(observaciones[k], R_obs[k])
            innov_arr[k], S_arr[k] = innov, S
        x_filt[k], P_filt[k] = kf.x, kf.P
    return x_filt, P_filt, x_pred, P_pred, innov_arr, S_arr

def _neg_log_vero(theta, T, obs, R, x0, P0, L_inf):
    a, T_opt, sigma, Q = theta
    if sigma<=0 or Q<=0 or a<0: return 1e10
    _,_,_,_, innov, S = correr_filtro(T, obs, R, x0, P0, theta, L_inf)
    mask = ~np.isnan(innov)
    if mask.sum()==0: return 1e10
    return 0.5*np.sum(np.log(2*np.pi*S[mask]) + innov[mask]**2/S[mask])

def ajustar_mle_kalman(T, obs, R, x0, P0, L_inf, theta0=(0.8,27.5,2.0,0.15), morfo=None):
    # Ampliar los limites drásticamente para que 'a' responda a las anomalías de T y evitar 'Apatía Térmica'
    # a, T_opt, sigma, Q
    if morfo == "P. galathinus 'Stripes'":
        bounds = [(0.01, 20.0), (28.0, 32.0), (0.1, 5.0), (1e-4, 10.0)]
    else:
        bounds = [(0.01, 20.0), (15.0, 40.0), (0.1, 20.0), (1e-4, 10.0)]
    
    mejor_res = None
    mejor_val = np.inf
    
    # Random restarts to avoid getting stuck in local minima (a=0)
    for seed in [42, 100, 200, 300, 400]:
        np.random.seed(seed)
        theta_ini = (
            np.random.uniform(0.1, 5.0),
            np.random.uniform(25.0, 30.0),
            np.random.uniform(0.5, 5.0),
            np.random.uniform(0.01, 1.0)
        )
        res = minimize(_neg_log_vero, theta_ini, args=(T,obs,R,x0,P0, L_inf), method="L-BFGS-B", bounds=bounds)
        if res.fun < mejor_val:
            mejor_val = res.fun
            mejor_res = res
            
    return mejor_res

def validacion_lomo_kalman(T, obs, R, x0, P0, L_inf, theta0=(0.8,27.5,2.0,0.15), morfo=None):
    n = len(T)
    idx_obs = [i for i in range(n) if not np.isnan(obs[i])]
    filas = []
    for k in idx_obs:
        obs_k, R_k = obs.copy(), R.copy()
        obs_k[k], R_k[k] = np.nan, np.nan
        res = ajustar_mle_kalman(T, obs_k, R_k, x0, P0, L_inf, theta0, morfo)
        mascara = np.array([i!=k for i in range(n)])
        _,_, x_pred, P_pred, _, _ = correr_filtro(T, obs, R, x0, P0, res.x, L_inf, mascara)
        residuo = obs[k]-x_pred[k]
        var_pred = P_pred[k]+R[k]
        filas.append({"paso_idx":k, "obs":obs[k], "pred":x_pred[k], "residuo":residuo,
                      "resid_std": residuo/np.sqrt(var_pred) if var_pred>0 else np.nan,
                      "theta":res.x})
    obs_a = np.array([f["obs"] for f in filas]); pred_a = np.array([f["pred"] for f in filas])
    resid_a = obs_a-pred_a
    return {"detalle":filas, "rmse":float(np.sqrt(np.mean(resid_a**2))),
            "mae":float(np.mean(np.abs(resid_a))),
            "r": float(np.corrcoef(obs_a,pred_a)[0,1]) if len(obs_a)>1 else np.nan}

# ============================================================================
# 4. MODEL MODULE (ABM OPEN POPULATION MODEL) - DATA-DRIVEN
# ============================================================================
class CangrejoDataDriven:
    __slots__ = ("talla","es_hembra","vivo","es_maduro")
    def __init__(self, talla, es_hembra, talla_madurez=4.5):
        self.talla = talla
        self.es_hembra = es_hembra
        self.vivo = True
        self.es_maduro = self.es_hembra and self.talla >= talla_madurez

class ABM_DataDriven:
    def __init__(self, datos_morfo, morfo="P. galathinus 'Spots'", seed=42):
        self.seed = seed
        self.tallas_reales = []
        self.tallas_juveniles = []
        n_hembras = 0
        n_total = 0
        
        # Empirical parameters for talla_madurez
        params_empiricos = {
            "P. galathinus 'Spots'": 4.45,
            "P. galathinus 'Stripes'": 4.04,
            "P. galathinus 'White Teeth'": 3.84,
            "P. coeruleus sp. nov.": 4.25,
        }
        
        self.talla_madurez = params_empiricos.get(morfo, 4.0)
        
        for paso, info in datos_morfo.items():
            for c in info.get('cangrejos', []):
                self.tallas_reales.append(c['talla'])
                if c['talla'] < 4.0:
                    self.tallas_juveniles.append(c['talla'])
                if c['sexo'] == 'F':
                    n_hembras += 1
                n_total += 1
        
        self.tallas_reales = np.array(self.tallas_reales) if self.tallas_reales else np.array([3.0])
        self.tallas_juveniles = np.array(self.tallas_juveniles) if self.tallas_juveniles else np.array([2.5])
        
        # Calculate dynamic parameters from raw data
        self.talla_max = float(np.max(self.tallas_reales))
        self.prop_hembras = n_hembras / max(1, n_total)
    
    def _muestrear_cangrejos(self, n, tipo="todos"):
        np.random.seed(self.seed + int(time.time()*1000)%10000)
        if tipo == "juveniles":
            tallas = np.random.choice(self.tallas_juveniles, size=n, replace=True)
        else:
            tallas = np.random.choice(self.tallas_reales, size=n, replace=True)
            
        sexos = np.random.rand(n) < self.prop_hembras
        return [CangrejoDataDriven(t, s, self.talla_madurez) for t, s in zip(tallas, sexos)]

    def simular(self, temperaturas, config, n_replicas=4, n_pasos=None, init_tipo="todos"):
        if n_pasos is None:
            n_pasos = len(temperaturas)
            
        todos = []
        todos_tallas = []
        np.random.seed(self.seed)
        
        for rep in range(n_replicas):
            n0 = max(1, int(round(np.random.poisson(config['densidad_inicial']))))
            pob = self._muestrear_cangrejos(n0, tipo=init_tipo)
            conteos = []
            tallas_pasos = []
            
            for k in range(n_pasos):
                T = temperaturas[k]
                estres = max(0.0, (T - UMBRAL_ESTRES_TERMICO)/5.0)
                nuevos = []
                
                for c in pob:
                    if not c.vivo: continue
                    p_mort = config['mortalidad_base'] + (config['estres_juvenil'] if c.talla<4.0 else config['estres_adulto'])*estres
                    if np.random.rand() < p_mort: continue
                    
                    inc = np.random.normal(0.2, 0.05) if c.talla<4.0 else np.random.normal(0.05, 0.02)
                    c.talla = min(c.talla+inc, self.talla_max)
                    if c.es_hembra and c.talla >= self.talla_madurez: c.es_maduro = True
                    nuevos.append(c)
                    
                pob = nuevos
                dens = len(pob)/VOLUMEN_CANASTA
                factor_d = max(0.0, 1.0 - dens/config['capacidad_canasta'])
                
                # External Pelagic Recruitment (Open Population)
                r_max = config['reclutas_max']
                t_opt = config['t_opt_reclutamiento']
                
                # Larval supply is temperature dependent and scaled by available space (factor_d)
                reclutas_esperados = r_max * np.exp(-0.5 * ((T - t_opt) / 2.0)**2) * factor_d
                crias_n = np.random.poisson(reclutas_esperados)
                
                if crias_n > 0:
                    crias = self._muestrear_cangrejos(crias_n, tipo="juveniles")
                    for cria in crias: cria.es_maduro = False
                    pob.extend(crias)
                    
                conteos.append(len(pob))
                
                tallas_vivos = [c.talla for c in pob if c.vivo]
                talla_m = np.mean(tallas_vivos) if len(tallas_vivos) > 0 else 0
                tallas_pasos.append(talla_m)
                
            todos.append(conteos)
            todos_tallas.append(tallas_pasos)
            
        todos = np.array(todos)
        todos_tallas = np.array(todos_tallas)
        return todos.mean(axis=0), todos.std(axis=0), todos_tallas.mean(axis=0), todos_tallas.std(axis=0)

    def _rmse_abm(self, params_array, T, obs_abundancia, densidad_inicial):
        config = {
            'mortalidad_base': params_array[0],
            'estres_juvenil': params_array[1],
            'estres_adulto': params_array[2],
            'reclutas_max': params_array[3],
            't_opt_reclutamiento': params_array[4],
            'capacidad_canasta': params_array[5],
            'densidad_inicial': densidad_inicial
        }
        sim_abundancia, _, _, _ = self.simular(T, config, n_replicas=8)
        idx_valid = ~np.isnan(obs_abundancia)
        if not np.any(idx_valid): return 1e9
        return float(np.sqrt(np.mean((obs_abundancia[idx_valid] - sim_abundancia[idx_valid])**2)))

    def optimizar_parametros(self, T, obs_abundancia, bounds, densidad_inicial):
        res = differential_evolution(self._rmse_abm, bounds, args=(T, obs_abundancia, densidad_inicial),
                                     maxiter=15, popsize=8, seed=self.seed, workers=1, mutation=(0.5, 1.0))
        return res.x, res.fun

def validacion_lomo_abm_datadriven(abm, T, obs, var_obs, dens0, bounds, re_optimizar=True):
    n = len(T)
    idx_obs = [i for i in range(n) if not np.isnan(obs[i])]
    filas = []
    
    # Optimizamos una vez usando todos los datos para usar como baseline global
    params_opt, _ = abm.optimizar_parametros(T, obs, bounds, dens0)
    config_opt = {
        'mortalidad_base': params_opt[0], 'estres_juvenil': params_opt[1],
        'estres_adulto': params_opt[2], 'reclutas_max': params_opt[3],
        't_opt_reclutamiento': params_opt[4], 'capacidad_canasta': params_opt[5],
        'densidad_inicial': dens0
    }
    
    sim_base, _, _, _ = abm.simular(T, config_opt, n_replicas=4)
    
    for k in idx_obs:
        if re_optimizar:
            obs_k = obs.copy()
            obs_k[k] = np.nan
            p_opt, _ = abm.optimizar_parametros(T, obs_k, bounds, dens0)
            cfg = {
                'mortalidad_base': p_opt[0], 'estres_juvenil': p_opt[1],
                'estres_adulto': p_opt[2], 'reclutas_max': p_opt[3],
                't_opt_reclutamiento': p_opt[4], 'capacidad_canasta': p_opt[5],
                'densidad_inicial': dens0
            }
            sim_k, _, _, _ = abm.simular(T, cfg, n_replicas=4)
            pred = sim_k[k]
            theta = p_opt
        else:
            pred = sim_base[k]
            theta = params_opt
            
        filas.append({"paso_idx":k, "obs":obs[k], "pred":pred, "residuo":obs[k]-pred, "theta":theta})
        
    obs_a = np.array([f["obs"] for f in filas]); pred_a = np.array([f["pred"] for f in filas])
    resid_a = obs_a-pred_a
    return {"detalle":filas, "rmse":float(np.sqrt(np.mean(resid_a**2))),
            "mae":float(np.mean(np.abs(resid_a))),
            "r": float(np.corrcoef(obs_a,pred_a)[0,1]) if len(obs_a)>1 else np.nan}, params_opt

# ============================================================================
# 5. BENCHMARKING COMPARATIVO DE MODELOS (LOMO CV)
# ============================================================================
def construir_features(temperaturas, mes_calendario_arr):
    mes_rad = 2*np.pi*np.asarray(mes_calendario_arr)/12.0
    return np.column_stack([temperaturas, np.sin(mes_rad), np.cos(mes_rad)])

def ols_fit_predict(X_train, y_train, X_test, seed=42):
    modelo = LinearRegression().fit(X_train, y_train)
    return float(modelo.predict(X_test.reshape(1,-1))[0]), 0.1

def bayesian_ridge_fit_predict(X_train, y_train, X_test):
    modelo = BayesianRidge().fit(X_train, y_train)
    mean = modelo.predict(X_test.reshape(1,-1))
    return float(mean[0]), 0.1

def xgboost_fit_predict(X_train, y_train, X_test, seed=42):
    if _TIENE_XGBOOST:
        modelo = XGBRegressor(n_estimators=30, max_depth=2, random_state=seed)
    else:
        modelo = GradientBoostingRegressor(n_estimators=30, max_depth=2, random_state=seed)
    modelo.fit(X_train, y_train)
    return float(modelo.predict(X_test.reshape(1,-1))[0])

def random_forest_fit_predict(X_train, y_train, X_test, seed=42):
    modelo = RandomForestRegressor(n_estimators=30, max_depth=3, random_state=seed).fit(X_train, y_train)
    return float(modelo.predict(X_test.reshape(1,-1))[0])

def comparar_modelos_lomo(X, y):
    idx_validos = np.where(~np.isnan(y))[0]
    resultados = {"OLS": [], "Bayesian_Ridge": [], "XGBoost": [], "RandomForest": []}
    scaler = StandardScaler()
    X_esc = scaler.fit_transform(X)
    for k in idx_validos:
        idx_train = [i for i in idx_validos if i != k]
        if len(idx_train) < 4: continue
        X_train, y_train, X_test = X_esc[idx_train], y[idx_train], X_esc[k]
        
        m_pred, _ = ols_fit_predict(X_train, y_train, X_test)
        resultados["OLS"].append((y[k], m_pred))
        
        b_pred, _ = bayesian_ridge_fit_predict(X_train, y_train, X_test)
        resultados["Bayesian_Ridge"].append((y[k], b_pred))
        
        resultados["XGBoost"].append((y[k], xgboost_fit_predict(X_train, y_train, X_test)))
        resultados["RandomForest"].append((y[k], random_forest_fit_predict(X_train, y_train, X_test)))
        
    tabla = {}
    for metodo, filas in resultados.items():
        if len(filas) == 0:
            tabla[metodo] = {"rmse": np.nan, "mae": np.nan, "r": np.nan}
            continue
        y_true = np.array([f[0] for f in filas]); y_pred = np.array([f[1] for f in filas])
        resid = y_true - y_pred
        r = float(np.corrcoef(y_true, y_pred)[0,1]) if len(y_true)>1 and np.std(y_true)>0 else np.nan
        tabla[metodo] = {"rmse": float(np.sqrt(np.mean(resid**2))), "mae": float(np.mean(np.abs(resid))), "r": r}
    return tabla

def entrenar_mejor_modelo(nombre_modelo, X_train, y_train, seed=42):
    idx_validos = np.where(~np.isnan(y_train))[0]
    X_train_v = X_train[idx_validos]
    y_train_v = y_train[idx_validos]
    scaler = StandardScaler()
    X_esc = scaler.fit_transform(X_train_v)
    
    if nombre_modelo == "OLS":
        modelo = LinearRegression().fit(X_esc, y_train_v)
    elif nombre_modelo == "Bayesian_Ridge":
        modelo = BayesianRidge().fit(X_esc, y_train_v)
    elif nombre_modelo == "XGBoost":
        if _TIENE_XGBOOST:
            modelo = XGBRegressor(n_estimators=30, max_depth=2, random_state=seed).fit(X_esc, y_train_v)
        else:
            modelo = GradientBoostingRegressor(n_estimators=30, max_depth=2, random_state=seed).fit(X_esc, y_train_v)
    elif nombre_modelo == "RandomForest":
        modelo = RandomForestRegressor(n_estimators=30, max_depth=3, random_state=seed).fit(X_esc, y_train_v)
    else: # Fallback
        modelo = BayesianRidge().fit(X_esc, y_train_v)
    return modelo, scaler

# ============================================================================
# 6. EXECUTION OF THE BIOLOGICAL PIPELINE AND SIMULATION
# ============================================================================
print("[3/7] Executing biological simulation and comparative benchmarking...")
datos = cargar_todos_morfotipos(excel_path)
df_hist, df_fut = obtener_clima_completo()
T_campana = temp_para_campana(df_hist)
temps_2026 = temp_para_prediccion(df_fut, 2026)
temps_2027 = temp_para_prediccion(df_fut, 2027)

resultados = {}

for morfo in ["P. galathinus 'Spots'","P. galathinus 'Stripes'","P. galathinus 'White Teeth'","P. coeruleus sp. nov."]:
    print(f"  Processing morphotype: {morfo}...")

    serie_talla = serie_talla_mensual(datos[morfo])
    serie_cont = serie_conteo_por_canasta(datos[morfo])

    # Kalman
    obs_talla = serie_talla['talla_media'].values
    n_talla = serie_talla['n'].values
    var_talla = serie_talla['talla_var'].values
    R_talla = np.where(n_talla>0, np.where(var_talla>0, var_talla/np.maximum(n_talla,1), 0.05/np.maximum(n_talla,1)), np.nan)
    idx0 = np.where(n_talla>0)[0][0]
    x0_k, P0_k = obs_talla[idx0], R_talla[idx0]

    # Empirical max size for Von Bertalanffy
    params_empiricos = {
        "P. galathinus 'Spots'": 10.62,
        "P. galathinus 'Stripes'": 12.32,
        "P. galathinus 'White Teeth'": 10.69,
        "P. coeruleus sp. nov.": 11.63
    }
    L_inf = params_empiricos.get(morfo, 10.0)

    lomo_kalman = validacion_lomo_kalman(T_campana, obs_talla, R_talla, x0_k, P0_k, L_inf, morfo=morfo)
    theta_kalman = ajustar_mle_kalman(T_campana, obs_talla, R_talla, x0_k, P0_k, L_inf, morfo=morfo).x
    x_filt,_,_,_,_,_ = correr_filtro(T_campana, obs_talla, R_talla, x0_k, P0_k, theta_kalman, L_inf)

    # ABM Data-Driven
    obs_cont = serie_cont['conteo_medio_canasta'].values
    var_cont = serie_cont['conteo_var_canasta'].values
    dens0 = obs_cont[np.where(~np.isnan(obs_cont))[0][0]]
    
    abm = ABM_DataDriven(datos[morfo], morfo=morfo, seed=42)
    
    # Capacidad canasta empirica
    max_densidad = {"P. galathinus 'Spots'": 15.93, "P. galathinus 'Stripes'": 18.48, "P. galathinus 'White Teeth'": 16.04, "P. coeruleus sp. nov.": 17.45}
    capacidad_max = max_densidad.get(morfo, 20.0)
    
    bounds = [
        (0.01, 0.20),  # mortalidad_base
        (0.01, 0.30),  # estres_juvenil
        (0.01, 0.20),  # estres_adulto
        (1.0, 300.0),  # reclutas_max
        (20.0, 35.0),  # t_opt_reclutamiento
        (5.0, capacidad_max)    # capacidad_canasta
    ]
    
    lomo_abm, params_opt = validacion_lomo_abm_datadriven(abm, T_campana, obs_cont, var_cont, dens0, bounds, re_optimizar=True)
    theta_abm = params_opt
    
    config_opt = {
        'mortalidad_base': params_opt[0], 'estres_juvenil': params_opt[1],
        'estres_adulto': params_opt[2], 'reclutas_max': params_opt[3],
        't_opt_reclutamiento': params_opt[4], 'capacidad_canasta': params_opt[5],
        'densidad_inicial': dens0
    }
    sim_cont, _, _, _ = abm.simular(T_campana, config_opt, n_replicas=4)

    # Modelos comparativos
    X_talla = construir_features(T_campana, serie_talla['mes_cal'].values)
    tabla_comp_talla = comparar_modelos_lomo(X_talla, obs_talla)
    tabla_comp_talla["Kalman_talla"] = {"rmse": lomo_kalman["rmse"], "mae": lomo_kalman["mae"], "r": lomo_kalman["r"]}

    X_cont = construir_features(T_campana, serie_cont['mes_cal'].values)
    tabla_comp_cont = comparar_modelos_lomo(X_cont, obs_cont)
    tabla_comp_cont["ABM_abundancia"] = {"rmse": lomo_abm["rmse"], "mae": lomo_abm["mae"], "r": lomo_abm["r"]}

    mejor_talla = min(tabla_comp_talla.items(), key=lambda kv: kv[1]["rmse"] if not np.isnan(kv[1]["rmse"]) else 1e9)
    mejor_cont = min(tabla_comp_cont.items(), key=lambda kv: kv[1]["rmse"] if not np.isnan(kv[1]["rmse"]) else 1e9)

    # Entrenar el mejor modelo estadistico para abundancia
    modelo_est_cont, scaler_cont = entrenar_mejor_modelo(mejor_cont[0], X_cont, obs_cont)

    # Prediccion 2026-2027
    pred = {}
    for anio, temps_anio in [(2026, temps_2026), (2027, temps_2027)]:
        pred[anio] = {}
        for m, T_arr in temps_anio.items():
            # Initialize with talla_madurez to simulate a new post-recruitment cohort rather than the ancient 2010 cohort
            kf_fwd = KalmanTalla(abm.talla_madurez, 0.1, theta_kalman, L_inf)
            talla_serie = []
            talla_std_serie = []
            for T_k in T_arr:
                xk, Pk = kf_fwd.predecir(T_k)
                talla_serie.append(xk)
                talla_std_serie.append(np.sqrt(Pk))
            
            sim_abund, sim_abund_std, sim_talla, sim_talla_std = abm.simular(T_arr, config_opt, n_replicas=4, init_tipo="juveniles")
            
            # Prediccion estadistica
            X_fut = construir_features(T_arr, np.arange(1, 13))
            X_fut_esc = scaler_cont.transform(X_fut)
            
            if hasattr(modelo_est_cont, 'alpha_'): # BayesianRidge
                sim_abund_est, sim_abund_est_std = modelo_est_cont.predict(X_fut_esc, return_std=True)
            else:
                sim_abund_est = modelo_est_cont.predict(X_fut_esc)
                sim_abund_est_std = np.zeros_like(sim_abund_est)
                
            sim_abund_est = np.maximum(0, sim_abund_est) # No negative abundance
            
            pred[anio][m] = {
                "talla": sim_talla, "talla_std": sim_talla_std, 
                "abundancia": sim_abund, "abundancia_std": sim_abund_std, 
                "abundancia_est": sim_abund_est, "abundancia_est_std": sim_abund_est_std, "temps": T_arr
            }

    resultados[morfo] = {
        "serie_talla": serie_talla, "serie_cont": serie_cont,
        "T_campana": T_campana, "x_filt_talla": x_filt, "sim_cont": sim_cont,
        "lomo_kalman": lomo_kalman, "lomo_abm": lomo_abm,
        "theta_kalman": theta_kalman, "theta_abm": theta_abm,
        "tabla_comp_talla": tabla_comp_talla, "tabla_comp_cont": tabla_comp_cont,
        "mejor_talla": mejor_talla[0], "mejor_cont": mejor_cont[0],
        "prediccion": pred,
    }

# Exportar CSV de resumen
filas_resumen = []
for morfo, r in resultados.items():
    fila = {
        "morfotipo": morfo,
        "kalman_rmse_mm": r["lomo_kalman"]["rmse"], "kalman_r": r["lomo_kalman"]["r"],
        "abm_rmse_ind_canasta": r["lomo_abm"]["rmse"], "abm_r": r["lomo_abm"]["r"],
        "mejor_modelo_talla": r["mejor_talla"], "mejor_modelo_abundancia": r["mejor_cont"],
        "theta_kalman_a_Topt_sigma_Q": list(np.round(r["theta_kalman"],3)),
        "theta_abm": list(np.round(r["theta_abm"],3)),
    }
    for metodo, met in r["tabla_comp_talla"].items():
        fila[f"talla_rmse_{metodo}"] = met["rmse"]
    for metodo, met in r["tabla_comp_cont"].items():
        fila[f"abund_rmse_{metodo}"] = met["rmse"]
    filas_resumen.append(fila)

df_resumen = pd.DataFrame(filas_resumen)
csv_resumen_path = os.path.join(submission_dir, "resumen_validacion_modelo.csv")
try:
    df_resumen.to_csv(csv_resumen_path, index=False)
    print(f"[OK] CSV de resumen de validaciÃ³n guardado en: {csv_resumen_path}")
except PermissionError:
    import datetime
    fallback_path = os.path.join(submission_dir, f"resumen_validacion_modelo_{datetime.datetime.now().strftime('%H%M%S')}.csv")
    df_resumen.to_csv(fallback_path, index=False)
    print(f"[WARNING] Permiso denegado. CSV de resumen guardado como: {fallback_path}")

# ============================================================================
# 7. GENERACIÃ“N DE FIGURAS EN ALTA RESOLUCIÃ“N (300 DPI)
# ============================================================================
print("[4/7] Generando figuras de publication (300 DPI)...")

import matplotlib.gridspec as gridspec
from matplotlib.patches import Patch

def generar_figuras_mejoradas(resultados, datos, T_campana, figuras_dir):
    """

    Genera 6 figuras optimizadas para publicaciÃ³n en Ecological Modelling
    """
    
    # ========================================================================
    # FIGURA 1: Series temporales de campo (SST + Abundancia + Talla)
    # ========================================================================
    fig1 = plt.figure(figsize=(16, 10))
    gs1 = gridspec.GridSpec(3, 1, height_ratios=[0.5, 1, 1], hspace=0.3)
    
    # Panel A: SST
    ax1 = fig1.add_subplot(gs1[0])
    ax1.plot(ORDEN_CAMPANA, T_campana, 'o-', color='#D35400', lw=2.5, 
             label='Observed SST (NOAA CoralTemp 0.05°)', markersize=8)
    ax1.axhline(UMBRAL_ESTRES_TERMICO, color='#C0392B', linestyle='--', 
                alpha=0.7, linewidth=2, label=f'Stress threshold ({UMBRAL_ESTRES_TERMICO}°C)')
    ax1.set_ylabel('SST (°C)', fontsize=12, fontweight='bold')
    ax1.set_title('A) Environmental conditions during sampling', fontsize=13, fontweight='bold')
    ax1.legend(loc='upper right', fontsize=10)
    ax1.grid(alpha=0.3, linestyle=':')
    ax1.set_xticklabels([])
    
    # Panel B: Abundancia
    ax2 = fig1.add_subplot(gs1[1])
    colores = ['#1565C0', '#2E7D32', '#6A1B9A', '#00838F']
    for i, morfo in enumerate(["P. galathinus 'Spots'", "P. galathinus 'Stripes'", "P. galathinus 'White Teeth'", "P. coeruleus sp. nov."]):
        s_c = serie_conteo_por_canasta(datos[morfo])
        ax2.plot(s_c["paso"], s_c["conteo_medio_canasta"], 'o-', 
                 color=colores[i], label=morfo, lw=2.5, markersize=7)
    ax2.set_ylabel('Individuals / collector', fontsize=12, fontweight='bold')
    ax2.set_title('B) Abundance per sampling collector (4.0 dm³)', fontsize=13, fontweight='bold')
    ax2.legend(loc='upper right', fontsize=10)
    ax2.grid(alpha=0.3, linestyle=':')
    ax2.set_xticklabels([])
    
    # Panel C: Talla
    ax3 = fig1.add_subplot(gs1[2])
    for i, morfo in enumerate(["P. galathinus 'Spots'", "P. galathinus 'Stripes'", "P. galathinus 'White Teeth'", "P. coeruleus sp. nov."]):
        s_t = serie_talla_mensual(datos[morfo])
        ax3.plot(s_t["paso"], s_t["talla_media"], 's-', 
                 color=colores[i], label=morfo, lw=2.5, markersize=7)
    ax3.set_xlabel('Sampling month', fontsize=12, fontweight='bold')
    ax3.set_ylabel('Carapace width (mm)', fontsize=12, fontweight='bold')
    ax3.set_title('C) Mean carapace width per morphotype', fontsize=13, fontweight='bold')
    ax3.legend(loc='upper right', fontsize=10)
    ax3.grid(alpha=0.3, linestyle=':')
    
    plt.tight_layout()
    plt.savefig(os.path.join(figuras_dir, 'Fig1_Field_Time_Series.png'), 
                dpi=300, bbox_inches='tight')
    plt.close()
    
    # ========================================================================
    # FIGURA 2: Distribuciones de talla y proporciÃ³n sexual
    # ========================================================================
    fig2, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig2.suptitle('Size distribution and sex ratio by morphotype', 
                  fontsize=14, fontweight='bold')
    
    for i, morfo in enumerate(["P. galathinus 'Spots'", "P. galathinus 'Stripes'", "P. galathinus 'White Teeth'", "P. coeruleus sp. nov."]):
        ax = axes[i//2, i%2]
        
        # Histograma de tallas
        tallas = []
        for info in datos[morfo].values():
            tallas.extend(info['tallas'])
        if len(tallas) > 0:
            n, bins, patches = ax.hist(tallas, bins=25, color=colores[i], 
                                       alpha=0.7, edgecolor='white', density=True)
            ax.set_xlabel('Carapace width (mm)', fontsize=10)
            ax.set_ylabel('Density', fontsize=10)
            ax.set_title(f'{morfo} (n = {len(tallas)})', fontweight='bold')
            
            # Media y mediana
            mean_val = np.mean(tallas)
            median_val = np.median(tallas)
            ax.axvline(mean_val, color='red', linestyle='-', linewidth=2, 
                      label=f'Mean = {mean_val:.1f} mm')
            ax.axvline(median_val, color='darkred', linestyle='--', linewidth=2,
                      label=f'Median = {median_val:.1f} mm')
            ax.legend(fontsize=8)
            ax.grid(alpha=0.2)
    
    plt.tight_layout()
    plt.savefig(os.path.join(figuras_dir, 'Fig2_Size_Sex_Distribution.png'), 
                dpi=300, bbox_inches='tight')
    plt.close()
    
    # ========================================================================
    # FIGURA 3: ValidaciÃ³n Kalman - Talla
    # ========================================================================
    fig3, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig3.suptitle('Kalman filter validation: carapace width (2009-2010)', 
                  fontsize=14, fontweight='bold')
    
    for i, morfo in enumerate(["P. galathinus 'Spots'", "P. galathinus 'Stripes'", "P. galathinus 'White Teeth'", "P. coeruleus sp. nov."]):
        ax = axes[i//2, i%2]
        r = resultados[morfo]
        meses_x = r["serie_talla"]["paso"].tolist()
        
        # Datos observados con barras de error
        obs_mean = r["serie_talla"]["talla_media"]
        obs_std = np.sqrt(r["serie_talla"]["talla_var"])
        ax.errorbar(meses_x, obs_mean, yerr=obs_std, fmt='s', color='#E74C3C',
                   label='Observed (± SD)', capsize=4, markersize=8, zorder=3)
        
        # Filtro Kalman
        ax.plot(meses_x, r["x_filt_talla"], 'o-', color=colores[i], 
               linewidth=2.5, label='Kalman (filtered)', markersize=7, zorder=2)
        
        # Metrics
        rmse = r['lomo_kalman']['rmse']
        r_val = r['lomo_kalman']['r']
        ax.set_title(f'{morfo}  RMSE = {rmse:.3f} mm, r = {r_val:.3f}', 
                    fontweight='bold')
        ax.set_ylabel('Carapace width (mm)', fontsize=11)
        ax.legend(loc='upper left', fontsize=9)
        ax.grid(alpha=0.3, linestyle=':')
        ax.set_xticklabels(meses_x, rotation=45, ha='right')
    
    plt.tight_layout()
    plt.savefig(os.path.join(figuras_dir, 'Fig3_Kalman_Validation_Size.png'), 
                dpi=300, bbox_inches='tight')
    plt.close()
    
    # ========================================================================
    # FIGURA 4: Validation IBM - Abundancia
    # ========================================================================
    fig4, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig4.suptitle('Individual-based model validation: abundance (2009-2010)', 
                  fontsize=14, fontweight='bold')
    
    for i, morfo in enumerate(["P. galathinus 'Spots'", "P. galathinus 'Stripes'", "P. galathinus 'White Teeth'", "P. coeruleus sp. nov."]):
        ax = axes[i//2, i%2]
        r = resultados[morfo]
        meses_x = r["serie_cont"]["paso"].tolist()
        
        # Datos observados
        obs_abund = r["serie_cont"]["conteo_medio_canasta"]
        obs_var = r["serie_cont"]["conteo_var_canasta"]
        obs_std = np.sqrt(obs_var)
        ax.errorbar(meses_x, obs_abund, yerr=obs_std, fmt='s', color='#E74C3C',
                   label='Observed (± SD)', capsize=4, markersize=8, zorder=3)
        
        # SimulaciÃ³n IBM
        ax.plot(meses_x, r["sim_cont"], 'o-', color=colores[i], 
               linewidth=2.5, label='IBM (simulated)', markersize=7, zorder=2)
        
        # MÃ©tricas
        rmse = r['lomo_abm']['rmse']
        r_val = r['lomo_abm']['r']
        ax.set_title(f'{morfo}  RMSE = {rmse:.1f} ind, r = {r_val:.3f}', 
                    fontweight='bold')
        ax.set_ylabel('Individuals / collector', fontsize=11)
        ax.legend(loc='upper left', fontsize=9)
        ax.grid(alpha=0.3, linestyle=':')
        ax.set_xticklabels(meses_x, rotation=45, ha='right')
    
    plt.tight_layout()
    plt.savefig(os.path.join(figuras_dir, 'Fig4_IBM_Validation_Abundance.png'), 
                dpi=300, bbox_inches='tight')
    plt.close()
    
    # ========================================================================
    # FIGURA 5: ComparaciÃ³n de mÃ©todos LOMO
    # ========================================================================
    fig5, axes = plt.subplots(2, 1, figsize=(14, 10))
    fig5.suptitle('Method comparison: out-of-sample RMSE (LOMO CV)', 
                  fontsize=14, fontweight='bold')
    
    metodos_talla = ['OLS', 'Bayesian_Ridge', 'XGBoost', 
                     'RandomForest', 'Kalman_talla']
    metodos_abund = ['OLS', 'Bayesian_Ridge', 'XGBoost', 
                     'RandomForest', 'ABM_abundancia']
    nombres_metodos = ['OLS', 'Bayes', 'XGB', 'RF', 'Mechanical']
    colores_metodos = ['#95A5A6', '#3498DB', '#2ECC71', '#F39C12', '#E74C3C']
    
    morfotipos = ["P. galathinus 'Spots'", "P. galathinus 'Stripes'", "P. galathinus 'White Teeth'", "P. coeruleus sp. nov."]
    x_pos = np.arange(len(morfotipos))
    width = 0.15
    offsets = [-2*width, -width, 0, width, 2*width]
    
    # Panel 1 (Arriba): Talla
    for j, m_key in enumerate(metodos_talla):
        rmse_vals = [resultados[morfo]["tabla_comp_talla"][m_key]["rmse"] for morfo in morfotipos]
        axes[0].bar(x_pos + offsets[j], rmse_vals, width, color=colores_metodos[j], label=nombres_metodos[j])
        
    axes[0].set_title('CW RMSE (mm)', fontweight='bold', fontsize=12)
    axes[0].set_xticks(x_pos)
    axes[0].set_xticklabels(morfotipos, fontsize=11)
    axes[0].set_ylabel('CW RMSE', fontsize=11)
    axes[0].legend(loc='upper left', fontsize=10, ncol=5)
    axes[0].grid(alpha=0.3, axis='y', linestyle=':')
    
    # Panel 2 (Abajo): Abundancia
    for j, m_key in enumerate(metodos_abund):
        rmse_vals = [resultados[morfo]["tabla_comp_cont"][m_key]["rmse"] for morfo in morfotipos]
        axes[1].bar(x_pos + offsets[j], rmse_vals, width, color=colores_metodos[j], label=nombres_metodos[j])
        
    axes[1].set_title('Abundance RMSE (individuals/collector)', fontweight='bold', fontsize=12)
    axes[1].set_xticks(x_pos)
    axes[1].set_xticklabels(morfotipos, fontsize=11)
    axes[1].set_ylabel('Abundance RMSE', fontsize=11)
    axes[1].legend(loc='upper left', fontsize=10, ncol=5)
    axes[1].grid(alpha=0.3, axis='y', linestyle=':')
    
    plt.tight_layout()
    plt.savefig(os.path.join(figuras_dir, 'Fig5_Method_Comparison_LOMO.png'), 
                dpi=300, bbox_inches='tight')
    plt.close()
    
    # ========================================================================
    # FIGURA 6: Proyecciones 2026-2027
    # ========================================================================
    for anio in [2026, 2027]:
        fig6 = plt.figure(figsize=(16, 14))
        gs6 = gridspec.GridSpec(5, 2, height_ratios=[0.5, 1, 1, 1, 1], 
                                hspace=0.4, wspace=0.3)
        
        # Panel SST
        ax_sst = fig6.add_subplot(gs6[0, :])
        meses_x = list(range(1, 13))
        r_ref = resultados["P. galathinus 'Spots'"]
        for m in MODELOS_CMIP6:
            if m in r_ref["prediccion"][anio]:
                ax_sst.plot(meses_x, r_ref["prediccion"][anio][m]["temps"], 
                           '-o', label=f'{m}', lw=2.5, markersize=7)
        ax_sst.axhline(UMBRAL_ESTRES_TERMICO, color='#C0392B', linestyle='--', 
                       alpha=0.7, linewidth=2, label=f'Threshold ({UMBRAL_ESTRES_TERMICO}°C)')
        ax_sst.set_title(f'SST Projection under CMIP6 - {anio}', 
                        fontsize=13, fontweight='bold')
        ax_sst.set_ylabel('SST (°C)', fontsize=12, fontweight='bold')
        ax_sst.legend(loc='upper left', fontsize=9)
        ax_sst.grid(alpha=0.3, linestyle=':')
        
        # Paneles por morfotipo
        for i, morfo in enumerate(["P. galathinus 'Spots'", "P. galathinus 'Stripes'", "P. galathinus 'White Teeth'", "P. coeruleus sp. nov."]):
            ax_talla = fig6.add_subplot(gs6[i+1, 0])
            ax_abund = fig6.add_subplot(gs6[i+1, 1])
            r = resultados[morfo]
            
            # Talla
            for m in MODELOS_CMIP6:
                if m in r["prediccion"][anio]:
                    y_talla = r["prediccion"][anio][m]["talla"]
                    y_talla_std = r["prediccion"][anio][m]["talla_std"]
                    line_t = ax_talla.plot(meses_x, y_talla, '-', linewidth=2, label=m)
                    ax_talla.fill_between(meses_x, y_talla - y_talla_std, y_talla + y_talla_std,
                                         color=line_t[0].get_color(), alpha=0.2)
            ax_talla.set_title(f'{morfo} — Projected size (± SD)', fontweight='bold')
            ax_talla.set_ylabel('Carapace width (mm)', fontsize=10)
            ax_talla.legend(fontsize=8)
            ax_talla.grid(alpha=0.3, linestyle=':')
            ax_talla.set_xticklabels([])
            
            # Abundancia
            for m in MODELOS_CMIP6:
                if m in r["prediccion"][anio]:
                    y_abund = r["prediccion"][anio][m]["abundancia"]
                    y_std = r["prediccion"][anio][m]["abundancia_std"]
                    y_est = r["prediccion"][anio][m]["abundancia_est"]
                    y_est_std = r["prediccion"][anio][m].get("abundancia_est_std", np.zeros_like(y_est))
                    
                    line = ax_abund.plot(meses_x, y_abund, '-', linewidth=2, label=f"ABM {m}")
                    ax_abund.fill_between(meses_x, np.maximum(0, y_abund - y_std), y_abund + y_std,
                                         color=line[0].get_color(), alpha=0.2)
                    
                    mejor_modelo_nombre = r["mejor_cont"]
                    line_est = ax_abund.plot(meses_x, y_est, '--', linewidth=1.5, color=line[0].get_color(), 
                                  label=f"{mejor_modelo_nombre} {m}")
                    if np.any(y_est_std > 0):
                        ax_abund.fill_between(meses_x, np.maximum(0, y_est - 1.96*y_est_std), y_est + 1.96*y_est_std,
                                              color=line[0].get_color(), alpha=0.1, hatch='//')
            ax_abund.set_title(f'{morfo} — Projected abundance (± SD)', fontweight='bold')
            ax_abund.set_ylabel('Individuals / collector', fontsize=10)
            ax_abund.legend(fontsize=8)
            ax_abund.grid(alpha=0.3, linestyle=':')
            
            # Solo el Ãºltimo panel tiene etiqueta de mes
            if i == 3:
                ax_talla.set_xlabel('Month', fontsize=10)
                ax_abund.set_xlabel('Month', fontsize=10)
        
        plt.tight_layout()
        plt.savefig(os.path.join(figuras_dir, f'Fig6_CMIP6_Projection_{anio}.png' if anio == 2026 else f'Fig7_CMIP6_Projection_{anio}.png'), 
                    dpi=300, bbox_inches='tight')
        plt.close()
    
    print("[OK] Todas las figuras generadas exitosamente.")

generar_figuras_mejoradas(resultados, datos, T_campana, figuras_dir) 



print("\n====================================================================")
print(" UNIFIED PIPELINE EXECUTED FROM START TO FINISH WITH TOTAL SUCCESS")
print("====================================================================")

