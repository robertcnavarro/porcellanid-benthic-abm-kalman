

# ============================================================================
# PIPELINE COMPLETO - PORCELANIDOS GOLFO DE MORROSQUILLO
# Kalman filter (talla) + ABM (abundancia por canasta)
# Calibracion/validacion 2009-2010 (leave-one-month-out) + prediccion 2026-2027
# Para Google Colab (necesita internet para las APIs climaticas)
# ============================================================================

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import requests
import time
import warnings
from scipy.optimize import minimize, differential_evolution
from google.colab import files

warnings.filterwarnings('ignore')
np.random.seed(42)

LATITUD, LONGITUD = 9.45, -75.65
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

# ============================================================================
# 1. SUBIR EXCEL Y EXTRAER DATOS (version corregida)
# ============================================================================

def subir_archivo_colab():
    print("Sube el archivo Excel 'base de datos def (4).xlsx'")
    uploaded = files.upload()
    for filename in uploaded.keys():
        return filename
    return None

def _identificar_mes(valor):
    if not valor:
        return None
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
# 2. CLIMA REAL (Archive API historico + CMIP6 por modelo, SIN ajustes manuales)
# ============================================================================

def descargar_historico(lat, lon, inicio, fin):
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {"latitude": lat, "longitude": lon, "start_date": inicio, "end_date": fin,
              "daily": "temperature_2m_mean,temperature_2m_max,temperature_2m_min,precipitation_sum",
              "timezone": "America/Bogota"}
    r = requests.get(url, params=params, timeout=60)
    r.raise_for_status()
    df = pd.DataFrame(r.json()['daily'])
    df['time'] = pd.to_datetime(df['time'])
    df['year'], df['month'] = df['time'].dt.year, df['time'].dt.month
    return df.groupby(['year','month']).agg(
        temperature_2m_mean=('temperature_2m_mean','mean'),
        precipitation_sum=('precipitation_sum','sum')).reset_index()

def descargar_cmip6_modelo(lat, lon, inicio, fin, modelo):
    url = "https://climate-api.open-meteo.com/v1/climate"
    params = {"latitude": lat, "longitude": lon, "start_date": inicio, "end_date": fin,
              "models": modelo,
              "daily": "temperature_2m_mean,temperature_2m_max,temperature_2m_min,precipitation_sum",
              "cell_selection": "land", "timezone": "America/Bogota"}
    r = requests.get(url, params=params, timeout=60)
    r.raise_for_status()
    datos = r.json()
    if 'daily' not in datos:
        print(f"  AVISO: sin datos para {modelo}")
        return None
    df = pd.DataFrame(datos['daily'])
    df['time'] = pd.to_datetime(df['time'])
    df['year'], df['month'] = df['time'].dt.year, df['time'].dt.month
    out = df.groupby(['year','month']).agg(
        temperature_2m_mean=('temperature_2m_mean','mean'),
        precipitation_sum=('precipitation_sum','sum')).reset_index()
    out['modelo'] = modelo
    return out

def obtener_clima_completo():
    print("Descargando historico 2009-2010 (Archive API)...")
    df_hist = descargar_historico(LATITUD, LONGITUD, "2009-01-01", "2010-12-31")
    df_hist['modelo'] = 'observado'

    print("Descargando CMIP6 2026-2027 (por modelo, sin ajustes manuales)...")
    dfs = []
    for m in MODELOS_CMIP6:
        d = descargar_cmip6_modelo(LATITUD, LONGITUD, "2026-01-01", "2027-12-31", m)
        if d is not None: dfs.append(d)
        time.sleep(1)
    df_fut = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()
    return df_hist, df_fut

def temp_para_campana(df_hist):
    """Alinea la serie Nov2009->Nov2010 de la campana con temperatura real observada."""
    temps = []
    for paso in ORDEN_CAMPANA:
        anio, mes = ANIO_CAMPANA[paso], MES_CALENDARIO[paso]
        fila = df_hist[(df_hist['year']==anio) & (df_hist['month']==mes)]
        temps.append(float(fila['temperature_2m_mean'].values[0]) if len(fila)>0 else np.nan)
    return np.array(temps)

def temp_para_prediccion(df_fut, anio):
    """12 temperaturas mensuales (ensemble CMIP6: media y por-modelo) para un anio."""
    sub = df_fut[df_fut['year']==anio]
    por_modelo = {}
    for m in MODELOS_CMIP6:
        s = sub[sub['modelo']==m].sort_values('month')
        if len(s)==12:
            por_modelo[m] = s['temperature_2m_mean'].values
    return por_modelo  # dict modelo -> array(12,)

# ============================================================================
# 3. FILTRO DE KALMAN - TALLA MEDIA POR MORFOTIPO
# ============================================================================

def g_crecimiento(T, a, T_opt, sigma):
    return a * np.exp(-0.5 * ((T - T_opt) / sigma) ** 2)

class KalmanTalla:
    def __init__(self, x0, P0, theta):
        self.x, self.P = x0, P0
        self.a, self.T_opt, self.sigma, self.Q = theta
    def predecir(self, T_k):
        self.x = self.x + g_crecimiento(T_k, self.a, self.T_opt, self.sigma)
        self.P = self.P + self.Q
        return self.x, self.P
    def actualizar(self, z_k, R_k):
        innov = z_k - self.x
        S = self.P + R_k
        K = self.P / S
        self.x = self.x + K*innov
        self.P = (1-K)*self.P
        return innov, S

def correr_filtro(temperaturas, observaciones, R_obs, x0, P0, theta, pasos_con_actualizacion=None):
    n = len(temperaturas)
    kf = KalmanTalla(x0, P0, theta)
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

def _neg_log_vero(theta, T, obs, R, x0, P0):
    a, T_opt, sigma, Q = theta
    if sigma<=0 or Q<=0 or a<0: return 1e10
    _,_,_,_, innov, S = correr_filtro(T, obs, R, x0, P0, theta)
    mask = ~np.isnan(innov)
    if mask.sum()==0: return 1e10
    return 0.5*np.sum(np.log(2*np.pi*S[mask]) + innov[mask]**2/S[mask])

def ajustar_mle_kalman(T, obs, R, x0, P0, theta0=(1.0,27.5,2.0,0.3)):
    bounds = [(0.0,5.0),(20.0,35.0),(0.3,10.0),(1e-4,5.0)]
    return minimize(_neg_log_vero, theta0, args=(T,obs,R,x0,P0), method="L-BFGS-B", bounds=bounds)

def validacion_lomo_kalman(T, obs, R, x0, P0, theta0=(1.0,27.5,2.0,0.3)):
    n = len(T)
    idx_obs = [i for i in range(n) if not np.isnan(obs[i])]
    filas = []
    for k in idx_obs:
        obs_k, R_k = obs.copy(), R.copy()
        obs_k[k], R_k[k] = np.nan, np.nan
        res = ajustar_mle_kalman(T, obs_k, R_k, x0, P0, theta0)
        mascara = np.array([i!=k for i in range(n)])
        _,_, x_pred, P_pred, _, _ = correr_filtro(T, obs, R, x0, P0, res.x, mascara)
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
# 4. ABM - ABUNDANCIA POR CANASTA
# ============================================================================

class Cangrejo:
    __slots__ = ("talla","es_hembra","vivo","es_maduro")
    def __init__(self, tm, ts, tmin, tmax, ph, tmad):
        self.talla = max(tmin, min(np.random.normal(tm, ts), tmax))
        self.es_hembra = np.random.rand() < ph
        self.vivo = True
        self.es_maduro = self.es_hembra and self.talla >= tmad

def simular_canasta(params, temperaturas, n_pasos, densidad_inicial, n_replicas=10,
                     umbral=UMBRAL_ESTRES_TERMICO):
    todos = []
    for _ in range(n_replicas):
        n0 = max(1, int(round(np.random.poisson(densidad_inicial))))
        pob = [Cangrejo(params['talla_media'],params['talla_std'],params['talla_min'],
                        params['talla_max'],params['prop_hembras'],params['talla_madurez']) for _ in range(n0)]
        conteos = []
        for k in range(n_pasos):
            T = temperaturas[k]
            estres = max(0.0, (T-umbral)/5.0)
            nuevos = []
            for c in pob:
                if not c.vivo: continue
                p_mort = params['mortalidad_base'] + (params['estres_juvenil'] if c.talla<4.0
                          else params['estres_adulto'])*estres
                if np.random.rand() < p_mort:
                    continue
                inc = np.random.normal(0.2,0.05) if c.talla<4.0 else np.random.normal(0.05,0.02)
                c.talla = min(c.talla+inc, params['talla_max'])
                if c.es_hembra and c.talla>=params['talla_madurez']: c.es_maduro=True
                nuevos.append(c)
            pob = nuevos
            dens = len(pob)/VOLUMEN_CANASTA
            factor_d = max(0.0, 1.0 - dens/params['capacidad_canasta'])
            crias = []
            for c in pob:
                if c.vivo and c.es_hembra and c.es_maduro and np.random.rand()<params['prob_reprod']*factor_d:
                    n_huevos = max(5, min(80, int(20+10*(c.talla-4.0))))
                    n_desc = min(10, int(n_huevos*params['supervivencia_huevos']*factor_d))
                    for _ in range(n_desc):
                        cria = Cangrejo(params['talla_media'],params['talla_std'],params['talla_min'],
                                        params['talla_max'],params['prop_hembras'],params['talla_madurez'])
                        cria.talla = max(1.5, min(3.5, np.random.normal(2.5,0.5)))
                        cria.es_maduro=False
                        crias.append(cria)
            pob.extend(crias)
            conteos.append(len(pob))
        todos.append(conteos)
    todos = np.array(todos)
    return todos.mean(axis=0), todos.std(axis=0)

BOUNDS_ABM = [(0.01,0.10),(0.02,0.35),(0.01,0.20),(0.05,0.30),(0.05,0.60),(5.0,60.0)]

def _params_vec(x, base):
    p = dict(base)
    p['mortalidad_base'],p['estres_juvenil'],p['estres_adulto'] = x[0],x[1],x[2]
    p['prob_reprod'],p['supervivencia_huevos'],p['capacidad_canasta'] = x[3],x[4],x[5]
    return p

def _obj_abm(x, base, T, obs, var_obs, n_pasos, dens0, n_rep):
    p = _params_vec(x, base)
    try: sim,_ = simular_canasta(p, T, n_pasos, dens0, n_rep)
    except Exception: return 1e6
    mask = ~np.isnan(obs)
    if mask.sum()==0: return 1e6
    pesos = np.where(np.isnan(var_obs)|(var_obs<=0), 1.0, 1.0/np.maximum(var_obs,1e-3))
    return float(np.sum(pesos[mask]*(obs[mask]-sim[mask])**2)/mask.sum())

def calibrar_abm(base, T, obs, var_obs, dens0, n_rep=10, maxiter=40, popsize=12, seed=42):
    return differential_evolution(_obj_abm, BOUNDS_ABM,
        args=(base,T,obs,var_obs,len(T),dens0,n_rep), maxiter=maxiter, popsize=popsize,
        seed=seed, polish=True)

def validacion_lomo_abm(base, T, obs, var_obs, dens0, n_rep=8, maxiter=20, popsize=8):
    n = len(T)
    idx_obs = [i for i in range(n) if not np.isnan(obs[i])]
    filas = []
    for k in idx_obs:
        obs_k, var_k = obs.copy(), var_obs.copy()
        obs_k[k], var_k[k] = np.nan, np.nan
        res = calibrar_abm(base, T, obs_k, var_k, dens0, n_rep, maxiter, popsize)
        p_hat = _params_vec(res.x, base)
        sim,_ = simular_canasta(p_hat, T, n, dens0, n_replicas=15)
        filas.append({"paso_idx":k, "obs":obs[k], "pred":sim[k], "residuo":obs[k]-sim[k], "theta":res.x})
    obs_a = np.array([f["obs"] for f in filas]); pred_a = np.array([f["pred"] for f in filas])
    resid_a = obs_a-pred_a
    return {"detalle":filas, "rmse":float(np.sqrt(np.mean(resid_a**2))),
            "mae":float(np.mean(np.abs(resid_a))),
            "r": float(np.corrcoef(obs_a,pred_a)[0,1]) if len(obs_a)>1 else np.nan}

# ============================================================================
# 5. MODELOS COMPARATIVOS: Monte Carlo (bootstrap), Bayesiano, XGBoost, RF
#    Validados con LOMO igual que Kalman/ABM -- comparacion justa, sin
#    circularidad (nunca se entrena y evalua con el mismo dato).
# ============================================================================
from sklearn.linear_model import BayesianRidge, LinearRegression
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler
try:
    from xgboost import XGBRegressor
    _TIENE_XGBOOST = True
except ImportError:
    from sklearn.ensemble import GradientBoostingRegressor
    _TIENE_XGBOOST = False

def construir_features(temperaturas, mes_calendario_arr):
    mes_rad = 2*np.pi*np.asarray(mes_calendario_arr)/12.0
    return np.column_stack([temperaturas, np.sin(mes_rad), np.cos(mes_rad)])

def montecarlo_bootstrap_fit_predict(X_train, y_train, X_test, n_boot=300, seed=42):
    rng = np.random.default_rng(seed)
    n = len(y_train)
    preds = np.zeros(n_boot)
    for b in range(n_boot):
        idx = rng.integers(0, n, size=n)
        Xb, yb = X_train[idx], y_train[idx]
        if len(np.unique(yb)) < 2:
            preds[b] = np.mean(yb); continue
        preds[b] = LinearRegression().fit(Xb, yb).predict(X_test.reshape(1,-1))[0]
    return float(np.mean(preds)), float(np.std(preds))

def bayesiano_fit_predict(X_train, y_train, X_test):
    modelo = BayesianRidge().fit(X_train, y_train)
    mean, std = modelo.predict(X_test.reshape(1,-1), return_std=True)
    return float(mean[0]), float(std[0])

def xgboost_fit_predict(X_train, y_train, X_test, seed=42):
    if _TIENE_XGBOOST:
        modelo = XGBRegressor(n_estimators=80, max_depth=2, learning_rate=0.1, reg_lambda=1.0, random_state=seed)
    else:
        modelo = GradientBoostingRegressor(n_estimators=80, max_depth=2, learning_rate=0.1, random_state=seed)
    modelo.fit(X_train, y_train)
    return float(modelo.predict(X_test.reshape(1,-1))[0])

def random_forest_fit_predict(X_train, y_train, X_test, seed=42):
    modelo = RandomForestRegressor(n_estimators=200, max_depth=3, random_state=seed).fit(X_train, y_train)
    return float(modelo.predict(X_test.reshape(1,-1))[0])

def comparar_modelos_lomo(X, y, n_boot_mc=300):
    """LOMO honesto para los 4 metodos ML/estadisticos, mismo criterio que Kalman/ABM."""
    idx_validos = np.where(~np.isnan(y))[0]
    resultados = {"MonteCarlo_bootstrap": [], "Bayesiano": [], "XGBoost": [], "RandomForest": []}
    scaler = StandardScaler()
    X_esc = scaler.fit_transform(X)
    for k in idx_validos:
        idx_train = [i for i in idx_validos if i != k]
        if len(idx_train) < 4:
            continue
        X_train, y_train, X_test = X_esc[idx_train], y[idx_train], X_esc[k]
        m_pred, m_std = montecarlo_bootstrap_fit_predict(X_train, y_train, X_test, n_boot_mc)
        resultados["MonteCarlo_bootstrap"].append((y[k], m_pred))
        b_pred, b_std = bayesiano_fit_predict(X_train, y_train, X_test)
        resultados["Bayesiano"].append((y[k], b_pred))
        resultados["XGBoost"].append((y[k], xgboost_fit_predict(X_train, y_train, X_test)))
        resultados["RandomForest"].append((y[k], random_forest_fit_predict(X_train, y_train, X_test)))
    tabla = {}
    for metodo, filas in resultados.items():
        if len(filas) == 0:
            tabla[metodo] = {"rmse": np.nan, "mae": np.nan, "r": np.nan}
            continue
        y_true = np.array([f[0] for f in filas]); y_pred = np.array([f[1] for f in filas])
        resid = y_true - y_pred
        r = float(np.corrcoef(y_true,y_pred)[0,1]) if len(y_true)>1 and np.std(y_true)>0 else np.nan
        tabla[metodo] = {"rmse": float(np.sqrt(np.mean(resid**2))), "mae": float(np.mean(np.abs(resid))), "r": r}
    return tabla

# ============================================================================
# 6. EJECUCION PRINCIPAL
# ============================================================================

if __name__ == "__main__":

    # --- datos biologicos ---
    file_path = subir_archivo_colab()
    datos = cargar_todos_morfotipos(file_path)

    # --- clima real ---
    df_hist, df_fut = obtener_clima_completo()
    T_campana = temp_para_campana(df_hist)  # 13 pasos, alineado a la campana real
    temps_2026 = temp_para_prediccion(df_fut, 2026)  # dict modelo -> 12 valores
    temps_2027 = temp_para_prediccion(df_fut, 2027)

    resultados = {}

    for morfo in ["P. galathinus 'Spots'","P. galathinus 'Stripes'","P. galathinus 'White Teeth'","P. coeruleus sp. nov."]:
        print(f"\n{'='*60}\n{morfo}\n{'='*60}")

        serie_talla = serie_talla_mensual(datos[morfo])
        serie_cont = serie_conteo_por_canasta(datos[morfo])

        # ---- Kalman: talla ----
        obs_talla = serie_talla['talla_media'].values
        n_talla = serie_talla['n'].values
        var_talla = serie_talla['talla_var'].values
        R_talla = np.where(n_talla>0, np.where(var_talla>0, var_talla/np.maximum(n_talla,1),
                            0.05/np.maximum(n_talla,1)), np.nan)
        idx0 = np.where(n_talla>0)[0][0]
        x0_k, P0_k = obs_talla[idx0], R_talla[idx0]

        lomo_kalman = validacion_lomo_kalman(T_campana, obs_talla, R_talla, x0_k, P0_k)
        print(f"  Kalman LOMO: RMSE={lomo_kalman['rmse']:.3f} mm  r={lomo_kalman['r']:.3f}")

        theta_kalman = ajustar_mle_kalman(T_campana, obs_talla, R_talla, x0_k, P0_k).x
        x_filt,_,_,_,_,_ = correr_filtro(T_campana, obs_talla, R_talla, x0_k, P0_k, theta_kalman)

        # ---- ABM: abundancia ----
        obs_cont = serie_cont['conteo_medio_canasta'].values
        var_cont = serie_cont['conteo_var_canasta'].values
        dens0 = obs_cont[np.where(~np.isnan(obs_cont))[0][0]]
        base_params = {
            'talla_media': float(np.nanmean(obs_talla)), 'talla_std': float(np.nanmean(var_talla))**0.5,
            'talla_min': 1.5, 'talla_max': 12.0, 'prop_hembras': 0.5, 'talla_madurez': 4.5,
        }
        lomo_abm = validacion_lomo_abm(base_params, T_campana, obs_cont, var_cont, dens0)
        print(f"  ABM LOMO: RMSE={lomo_abm['rmse']:.2f} ind/canasta  r={lomo_abm['r']:.3f}")

        theta_abm = calibrar_abm(base_params, T_campana, obs_cont, var_cont, dens0).x
        p_hat_abm = _params_vec(theta_abm, base_params)
        sim_cont,_ = simular_canasta(p_hat_abm, T_campana, len(T_campana), dens0, n_replicas=25)

        # ---- Modelos comparativos (Monte Carlo, Bayesiano, XGBoost, RF) ----
        X_talla = construir_features(T_campana, serie_talla['mes_cal'].values)
        tabla_comp_talla = comparar_modelos_lomo(X_talla, obs_talla)
        tabla_comp_talla["Kalman_talla"] = {"rmse": lomo_kalman["rmse"], "mae": lomo_kalman["mae"], "r": lomo_kalman["r"]}

        X_cont = construir_features(T_campana, serie_cont['mes_cal'].values)
        tabla_comp_cont = comparar_modelos_lomo(X_cont, obs_cont)
        tabla_comp_cont["ABM_abundancia"] = {"rmse": lomo_abm["rmse"], "mae": lomo_abm["mae"], "r": lomo_abm["r"]}

        mejor_talla = min(tabla_comp_talla.items(), key=lambda kv: kv[1]["rmse"] if not np.isnan(kv[1]["rmse"]) else 1e9)
        mejor_cont = min(tabla_comp_cont.items(), key=lambda kv: kv[1]["rmse"] if not np.isnan(kv[1]["rmse"]) else 1e9)
        print(f"  Mejor modelo TALLA (LOMO): {mejor_talla[0]} (RMSE={mejor_talla[1]['rmse']:.3f})")
        print(f"  Mejor modelo ABUNDANCIA (LOMO): {mejor_cont[0]} (RMSE={mejor_cont[1]['rmse']:.2f})")

        # ---- Prediccion 2026-2027 (ensemble CMIP6, por modelo) ----
        pred = {}
        for anio, temps_anio in [(2026, temps_2026), (2027, temps_2027)]:
            pred[anio] = {}
            for m, T_arr in temps_anio.items():
                x_talla_pred = [x_filt[-1]]
                kf_fwd = KalmanTalla(x_filt[-1], 0.1, theta_kalman)
                talla_serie = []
                for T_k in T_arr:
                    xk,_ = kf_fwd.predecir(T_k)
                    talla_serie.append(xk)
                sim_abund,_ = simular_canasta(p_hat_abm, T_arr, 12, dens0, n_replicas=25)
                pred[anio][m] = {"talla": np.array(talla_serie), "abundancia": sim_abund}

        resultados[morfo] = {
            "serie_talla": serie_talla, "serie_cont": serie_cont,
            "T_campana": T_campana, "x_filt_talla": x_filt, "sim_cont": sim_cont,
            "lomo_kalman": lomo_kalman, "lomo_abm": lomo_abm,
            "theta_kalman": theta_kalman, "theta_abm": theta_abm,
            "tabla_comp_talla": tabla_comp_talla, "tabla_comp_cont": tabla_comp_cont,
            "mejor_talla": mejor_talla[0], "mejor_cont": mejor_cont[0],
            "prediccion": pred,
        }

    # ========================================================================
    # FIGURA 1: VALIDACION 2009-2010 (talla y abundancia, datos reales vs modelo)
    # ========================================================================
    fig, axes = plt.subplots(4, 2, figsize=(14, 18))
    fig.suptitle('ValidaciÃ³n 2009-2010: talla (Kalman) y abundancia (ABM) â€” real vs. modelo',
                 fontsize=14, fontweight='bold')
    for i, morfo in enumerate(["P. galathinus 'Spots'","P. galathinus 'Stripes'","P. galathinus 'White Teeth'","P. coeruleus sp. nov."]):
        r = resultados[morfo]
        meses_x = r["serie_talla"]["paso"].tolist()

        ax = axes[i,0]
        ax.plot(meses_x, r["serie_talla"]["talla_media"], 's', color='red', label='Talla observada')
        ax.plot(meses_x, r["x_filt_talla"], 'o-', color=COLORES[morfo], label='Kalman (filtrado)')
        ax.set_title(f"{morfo} â€” Talla (LOMO RMSE={r['lomo_kalman']['rmse']:.2f} mm, r={r['lomo_kalman']['r']:.2f})")
        ax.set_ylabel('Talla media (mm)'); ax.tick_params(axis='x', rotation=45); ax.legend(fontsize=8); ax.grid(alpha=.3)

        ax2 = axes[i,1]
        ax2.plot(meses_x, r["serie_cont"]["conteo_medio_canasta"], 's', color='red', label='Obs. (ind/canasta)')
        ax2.plot(meses_x, r["sim_cont"], 'o-', color=COLORES[morfo], label='ABM')
        ax2.set_title(f"{morfo} â€” Abundancia (LOMO RMSE={r['lomo_abm']['rmse']:.1f}, r={r['lomo_abm']['r']:.2f})")
        ax2.set_ylabel('Individuos/canasta'); ax2.tick_params(axis='x', rotation=45); ax2.legend(fontsize=8); ax2.grid(alpha=.3)
    plt.tight_layout()
    plt.savefig('figura_validacion_2009_2010.png', dpi=300, bbox_inches='tight')
    plt.show()

    # ========================================================================
    # FIGURA 2: PREDICCION 2026 vs 2027 (paneles separados por aÃ±o)
    # ========================================================================
    for anio in [2026, 2027]:
        fig, axes = plt.subplots(4, 2, figsize=(14, 18))
        fig.suptitle(f'PredicciÃ³n {anio} (ensemble CMIP6, incertidumbre entre modelos)',
                     fontsize=14, fontweight='bold')
        meses_x = list(range(1,13))
        for i, morfo in enumerate(["P. galathinus 'Spots'","P. galathinus 'Stripes'","P. galathinus 'White Teeth'","P. coeruleus sp. nov."]):
            r = resultados[morfo]
            ax = axes[i,0]
            for m in MODELOS_CMIP6:
                if m in r["prediccion"][anio]:
                    ax.plot(meses_x, r["prediccion"][anio][m]["talla"], '-', alpha=.8, label=m)
            ax.set_title(f"{morfo} â€” Talla predicha {anio}")
            ax.set_ylabel('Talla media (mm)'); ax.legend(fontsize=7); ax.grid(alpha=.3)

            ax2 = axes[i,1]
            for m in MODELOS_CMIP6:
                if m in r["prediccion"][anio]:
                    ax2.plot(meses_x, r["prediccion"][anio][m]["abundancia"], '-', alpha=.8, label=m)
            ax2.set_title(f"{morfo} â€” Abundancia predicha {anio}")
            ax2.set_ylabel('Individuos/canasta'); ax2.legend(fontsize=7); ax2.grid(alpha=.3)
        plt.tight_layout()
        plt.savefig(f'figura_prediccion_{anio}.png', dpi=300, bbox_inches='tight')
        plt.show()

    # ========================================================================
    # FIGURA 3: COMPARACION DE METODOS (RMSE fuera de muestra, LOMO)
    # ========================================================================
    fig, axes = plt.subplots(4, 2, figsize=(14, 18))
    fig.suptitle('ComparaciÃ³n de mÃ©todos â€” RMSE fuera de muestra (LOMO)', fontsize=14, fontweight='bold')
    for i, morfo in enumerate(["P. galathinus 'Spots'","P. galathinus 'Stripes'","P. galathinus 'White Teeth'","P. coeruleus sp. nov."]):
        r = resultados[morfo]
        ax = axes[i,0]
        nombres = list(r["tabla_comp_talla"].keys())
        vals = [r["tabla_comp_talla"][n]["rmse"] for n in nombres]
        bars = ax.bar(nombres, vals, color=[COLORES[morfo] if n=="Kalman_talla" else "#999999" for n in nombres])
        ax.set_title(f"{morfo} â€” Talla: mejor = {r['mejor_talla']}")
        ax.set_ylabel('RMSE (mm)'); ax.tick_params(axis='x', rotation=30)

        ax2 = axes[i,1]
        nombres2 = list(r["tabla_comp_cont"].keys())
        vals2 = [r["tabla_comp_cont"][n]["rmse"] for n in nombres2]
        ax2.bar(nombres2, vals2, color=[COLORES[morfo] if n=="ABM_abundancia" else "#999999" for n in nombres2])
        ax2.set_title(f"{morfo} â€” Abundancia: mejor = {r['mejor_cont']}")
        ax2.set_ylabel('RMSE (ind/canasta)'); ax2.tick_params(axis='x', rotation=30)
    plt.tight_layout()
    plt.savefig('figura_comparacion_metodos.png', dpi=300, bbox_inches='tight')
    plt.show()

    # ========================================================================
    # EXPORTAR RESULTADOS
    # ========================================================================
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
    df_resumen.to_csv("resumen_validacion_modelo.csv", index=False)
    print("\n", df_resumen.to_string(index=False))

    files.download('figura_validacion_2009_2010.png')
    files.download('figura_comparacion_metodos.png')
    files.download('figura_prediccion_2026.png')
    files.download('figura_prediccion_2027.png')
    files.download('resumen_validacion_modelo.csv')

# ============================================================================
# MODELO ABM CON DATOS CLIMÃTICOS REALES (HISTÃ“RICOS + CMIP6)
# CALIBRACIÃ“N 2009-2010 Y PREDICCIONES 2026-2027
# VERSIÃ“N COMPLETA CON AMBAS APIs
# ============================================================================

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.stats import norm, pearsonr, gaussian_kde
from scipy.optimize import differential_evolution
from sklearn.metrics import mean_squared_error, r2_score, mean_absolute_error
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.preprocessing import StandardScaler
import warnings
import os
import time
import requests
from google.colab import files
import seaborn as sns

warnings.filterwarnings('ignore')
sns.set_style("whitegrid")
sns.set_palette("deep")

# ============================================================================
# CONFIGURACIÃ“N
# ============================================================================
VOLUMEN_CANASTA = 4.0  # dmÂ³
MESES_STR = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
MESES_ORDEN = ["Nov", "Dic", "Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Oct"]
UMBRAL_ESTRES_TERMICO = 28.5
RANDOM_SEED = 42
np.random.seed(RANDOM_SEED)

# Coordenadas del Golfo de Morrosquillo
LATITUD = 9.45
LONGITUD = -75.65

# ============================================================================
# 1. SUBIR ARCHIVO Y EXTRAER DATOS
# ============================================================================

def subir_archivo_colab():
    print("ðŸ“‚ Sube el archivo Excel 'base de datos def (4).xlsx'")
    uploaded = files.upload()
    for filename in uploaded.keys():
        print(f"âœ… Archivo subido: {filename}")
        return filename
    return None

def extraer_datos_completos(file_path):
    """Extrae todos los datos del Excel"""

    hojas = {
        "P. galathinus 'Spots'": "PUNTOS MESES",
        "P. galathinus 'Stripes'": "ESTRIAS MESES",
        "P. galathinus 'White Teeth'": "DB MESES",
        "P. coeruleus sp. nov.": "AZUL MESES"
    }

    datos_completos = {}

    for morfo, hoja in hojas.items():
        print(f"\nðŸ“– Leyendo {morfo} desde {hoja}...")
        df = pd.read_excel(file_path, sheet_name=hoja, header=None)

        tallas_por_mes = {}
        sexos_por_mes = {}
        mes_actual = None

        for col in range(df.shape[1]):
            valor = str(df.iloc[0, col]).upper().strip() if pd.notna(df.iloc[0, col]) else ""
            for mes in ["NOVIEMBRE", "DICIEMBRE", "ENERO", "FEBRERO", "MARZO", "ABRIL",
                       "MAYO", "JUNIO", "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE"]:
                if mes in valor:
                    mes_actual = mes[:3].capitalize()
                    tallas_por_mes[mes_actual] = []
                    sexos_por_mes[mes_actual] = []
                    break
            if mes_actual:
                sub_hdr = str(df.iloc[1, col]).upper().strip() if pd.notna(df.iloc[1, col]) else ""
                if "TAMA" in sub_hdr or "TALLA" in sub_hdr:
                    for row in range(2, df.shape[0]):
                        val = df.iloc[row, col]
                        if pd.notna(val) and val != 0:
                            try:
                                tallas_por_mes[mes_actual].append(float(val))
                            except:
                                pass
                elif "SEXO" in sub_hdr:
                    for row in range(2, df.shape[0]):
                        val = str(df.iloc[row, col]).upper().strip() if pd.notna(df.iloc[row, col]) else ""
                        if val in ['M', 'H', 'HO', 'F']:
                            sexos_por_mes[mes_actual].append('F' if val in ['H', 'HO', 'F'] else 'M')

        datos_completos[morfo] = {
            'tallas_por_mes': tallas_por_mes,
            'sexos_por_mes': sexos_por_mes,
            'conteos': {mes: len(tallas) for mes, tallas in tallas_por_mes.items()},
            'tallas_medias': {mes: np.mean(tallas) if tallas else 0 for mes, tallas in tallas_por_mes.items()},
            'tallas_std': {mes: np.std(tallas) if tallas else 0 for mes, tallas in tallas_por_mes.items()}
        }

        print(f"  Conteos: {datos_completos[morfo]['conteos']}")

    return datos_completos

# ============================================================================
# 2. OBTENER DATOS CLIMÃTICOS (HISTÃ“RICOS + CMIP6) - APIs CORRECTAS
# ============================================================================

def obtener_datos_historicos(lat, lon, inicio, fin):
    """
    Obtiene datos climÃ¡ticos histÃ³ricos de Open-Meteo Archive API
    Disponible: 1940 - presente
    """
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": inicio,
        "end_date": fin,
        "daily": "temperature_2m_mean,temperature_2m_max,temperature_2m_min,precipitation_sum",
        "timezone": "America/Bogota"
    }

    try:
        print(f"ðŸŒ Consultando Archive API para {inicio} a {fin}...")
        response = requests.get(url, params=params, timeout=60)
        if response.status_code == 200:
            datos = response.json()
            df = pd.DataFrame(datos['daily'])
            df['time'] = pd.to_datetime(df['time'])
            df['year'] = df['time'].dt.year
            df['month'] = df['time'].dt.month

            df_mensual = df.groupby(['year', 'month']).agg({
                'temperature_2m_mean': 'mean',
                'temperature_2m_max': 'mean',
                'temperature_2m_min': 'mean',
                'precipitation_sum': 'sum'
            }).reset_index()

            print(f"  âœ… Datos obtenidos: {len(df_mensual)} meses")
            print(f"  ðŸ“Š Temp media: {df_mensual['temperature_2m_mean'].mean():.1f}Â°C")
            return df_mensual
        else:
            print(f"  âŒ Error: {response.status_code}")
            print(f"     {response.text[:200]}")
            return None
    except Exception as e:
        print(f"  âŒ Error: {e}")
        return None

def obtener_datos_cmip6(lat, lon, inicio, fin):
    """
    Obtiene datos climÃ¡ticos proyectados de la Climate API (CMIP6)
    Disponible: 1950 - 2050
    Modelos: EC_Earth3P_HR, MRI_AGCM3_2_S (recomendados para El NiÃ±o)
    """
    url = "https://climate-api.open-meteo.com/v1/climate"
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": inicio,
        "end_date": fin,
        "models": "EC_Earth3P_HR,MRI_AGCM3_2_S",
        "daily": "temperature_2m_mean,temperature_2m_max,temperature_2m_min,precipitation_sum",
        "cell_selection": "land",
        "timezone": "America/Bogota"
    }

    try:
        print(f"ðŸŒ Consultando Climate API (CMIP6) para {inicio} a {fin}...")
        response = requests.get(url, params=params, timeout=60)
        if response.status_code == 200:
            datos = response.json()

            # Verificar que hay datos
            if 'daily' not in datos:
                print(f"  âŒ No hay datos diarios en la respuesta")
                print(f"     Respuesta: {datos}")
                return None

            df = pd.DataFrame(datos['daily'])
            df['time'] = pd.to_datetime(df['time'])
            df['year'] = df['time'].dt.year
            df['month'] = df['time'].dt.month

            # Verificar que las columnas existen
            columnas_requeridas = ['temperature_2m_mean', 'temperature_2m_max', 'temperature_2m_min', 'precipitation_sum']
            for col in columnas_requeridas:
                if col not in df.columns:
                    print(f"  âš ï¸ Columna {col} no encontrada, estimando...")
                    if col == 'temperature_2m_mean' and 'temperature_2m_max' in df.columns and 'temperature_2m_min' in df.columns:
                        df['temperature_2m_mean'] = (df['temperature_2m_max'] + df['temperature_2m_min']) / 2
                    elif col == 'precipitation_sum':
                        df['precipitation_sum'] = 0

            df_mensual = df.groupby(['year', 'month']).agg({
                'temperature_2m_mean': 'mean',
                'temperature_2m_max': 'mean',
                'temperature_2m_min': 'mean',
                'precipitation_sum': 'sum'
            }).reset_index()

            print(f"  âœ… Datos obtenidos: {len(df_mensual)} meses")
            print(f"  ðŸ“Š Temp media: {df_mensual['temperature_2m_mean'].mean():.1f}Â°C")
            return df_mensual
        else:
            print(f"  âŒ Error: {response.status_code}")
            print(f"     {response.text[:200]}")
            return None
    except Exception as e:
        print(f"  âŒ Error: {e}")
        return None

def obtener_clima_completo():
    """
    Obtiene datos climÃ¡ticos:
    - HistÃ³ricos: 2009-2010 (Archive API)
    - Futuros: 2026-2027 (Climate API - CMIP6)
    """
    print("\n" + "="*70)
    print("  OBTENIENDO DATOS CLIMÃTICOS")
    print("  ðŸ”¹ HistÃ³ricos: Open-Meteo Archive API (1940-presente)")
    print("  ðŸ”¹ Futuros: Open-Meteo Climate API CMIP6 (1950-2050)")
    print("="*70)

    dfs = []

    # 1. Datos histÃ³ricos 2009-2010
    print("\nðŸ“Š PERÃODO HISTÃ“RICO 2009-2010:")
    df_hist = obtener_datos_historicos(LATITUD, LONGITUD, "2009-01-01", "2010-12-31")
    if df_hist is not None:
        dfs.append(df_hist)
    else:
        print("  âš ï¸ Usando datos simulados para histÃ³rico")
        dfs.append(generar_datos_simulados_historicos())

    # 2. Datos futuros 2026-2027 (CMIP6)
    print("\nðŸ“Š PERÃODO FUTURO 2026-2027 (CMIP6 - Modelos para El NiÃ±o):")
    df_futuro = obtener_datos_cmip6(LATITUD, LONGITUD, "2026-01-01", "2027-12-31")

    if df_futuro is not None:
        # Ajustar ligeramente para escenario de El NiÃ±o (temperaturas mÃ¡s altas)
        # Esto es opcional ya que los modelos CMIP6 ya incluyen diferentes escenarios
        print("  ðŸŒ¡ï¸ Aplicando ajuste para escenario de El NiÃ±o (+0.5Â°C)")
        df_futuro['temperature_2m_mean'] = df_futuro['temperature_2m_mean'] + 0.5
        df_futuro['temperature_2m_max'] = df_futuro['temperature_2m_max'] + 0.5
        dfs.append(df_futuro)
    else:
        print("  âš ï¸ Usando datos simulados para futuro")
        dfs.append(generar_datos_simulados_futuro())

    # Combinar todos los datos
    df_completo = pd.concat(dfs, ignore_index=True)

    print(f"\nâœ… DATOS CLIMÃTICOS TOTALES: {len(df_completo)} meses")
    print(f"   AÃ±os: {df_completo['year'].unique().tolist()}")

    # Mostrar resumen de temperaturas por aÃ±o
    print("\nðŸ“Š RESUMEN DE TEMPERATURAS POR AÃ‘O:")
    for year in df_completo['year'].unique():
        temp_mean = df_completo[df_completo['year'] == year]['temperature_2m_mean'].mean()
        print(f"   {year}: {temp_mean:.1f}Â°C")

    return df_completo

def generar_datos_simulados_historicos():
    """Genera datos simulados para 2009-2010 (fallback)"""
    print("  Generando datos simulados para 2009-2010...")
    fechas = pd.date_range(start="2009-01-01", end="2010-12-31", freq='MS')
    datos = []

    for fecha in fechas:
        mes = fecha.month
        aÃ±o = fecha.year

        temp = 27.5 + 0.5 * np.sin((mes - 3) * 2 * np.pi / 12) + np.random.normal(0, 0.3)
        precip = 5 + 5 * np.sin((mes - 6) * 2 * np.pi / 12) + np.random.normal(0, 2)

        datos.append({
            'year': aÃ±o,
            'month': mes,
            'temperature_2m_mean': max(25, min(33, temp)),
            'temperature_2m_max': temp + 2,
            'temperature_2m_min': temp - 2,
            'precipitation_sum': max(0, precip)
        })

    return pd.DataFrame(datos)

def generar_datos_simulados_futuro():
    """Genera datos simulados para 2026-2027 (fallback)"""
    print("  Generando datos simulados para 2026-2027...")
    fechas = pd.date_range(start="2026-01-01", end="2027-12-31", freq='MS')
    datos = []

    for fecha in fechas:
        mes = fecha.month
        aÃ±o = fecha.year

        temp_extra = 0.5 if aÃ±o == 2026 else 0.8
        temp = 28.0 + 0.5 * np.sin((mes - 3) * 2 * np.pi / 12) + temp_extra + np.random.normal(0, 0.3)
        precip = 3 + 3 * np.sin((mes - 6) * 2 * np.pi / 12) + np.random.normal(0, 1)

        datos.append({
            'year': aÃ±o,
            'month': mes,
            'temperature_2m_mean': max(26, min(34, temp)),
            'temperature_2m_max': temp + 2,
            'temperature_2m_min': temp - 2,
            'precipitation_sum': max(0, precip)
        })

    return pd.DataFrame(datos)

# ============================================================================
# 3. CLASE CANGREJO CALIBRADO
# ============================================================================

class CangrejoCalibrado:
    def __init__(self, morfo, params, habitat='intermareal'):
        self.morfo = morfo
        p = params[morfo]
        talla_gen = np.random.normal(p['media'], p['std'])
        self.talla = max(p['talla_min'], min(talla_gen, p['talla_max']))
        self.es_hembra = np.random.rand() < p['prop_hembras']
        self.vivo = True
        self.edad = 0
        self.habitat = habitat
        self.migrando = False
        self.tiempo_migracion = 0
        self.es_maduro = self.talla >= p['talla_madurez'] and self.es_hembra

        self.mortalidad_base = params[morfo].get('mortalidad_base', 0.025)
        self.estres_juvenil = params[morfo].get('estres_juvenil', 0.15)
        self.estres_adulto = params[morfo].get('estres_adulto', 0.05)
        self.prob_reprod = params[morfo].get('prob_reprod', 0.12)
        self.supervivencia_huevos = params[morfo].get('supervivencia_huevos', 0.25)

    def sobrevivir_mes(self, temp, salinidad, oxigeno):
        if not self.vivo:
            return

        estres_temp = max(0, (temp - UMBRAL_ESTRES_TERMICO) / 5.0)
        estres_salinidad = abs(salinidad - 35.0) / 5.0
        estres_oxigeno = max(0, (4.0 - oxigeno) / 4.0)

        prob_mortalidad = self.mortalidad_base

        if self.talla < 4.0:
            prob_mortalidad += self.estres_juvenil * estres_temp
        else:
            prob_mortalidad += self.estres_adulto * estres_temp

        prob_mortalidad += 0.04 * estres_salinidad + 0.06 * estres_oxigeno

        if self.migrando:
            prob_mortalidad += 0.08

        if not self.migrando and self.talla > 4.0:
            prob_migrar = 0.01 + 0.04 * estres_temp + 0.02 * estres_salinidad
            if np.random.rand() < prob_migrar:
                self.migrando = True
                self.tiempo_migracion = 0

        if self.migrando:
            self.tiempo_migracion += 1
            if self.tiempo_migracion > 2:
                self.migrando = False
                self.tiempo_migracion = 0
                habitats = ['intermareal', 'sublitoral', 'arrecife']
                actual = habitats.index(self.habitat)
                nuevo = (actual + np.random.choice([-1, 1])) % len(habitats)
                self.habitat = habitats[nuevo]

        if np.random.rand() < prob_mortalidad:
            self.vivo = False
            return

        self.edad += 1
        if self.talla < 4.0:
            crecimiento = np.random.normal(0.2, 0.05)
        else:
            crecimiento = np.random.normal(0.05, 0.02)
        self.talla = min(self.talla + crecimiento, 12.0)

        if self.es_hembra and self.talla >= 4.5:
            self.es_maduro = True

    def reproducir(self, params, mes, densidad_hembras, temp):
        if not self.vivo or not self.es_hembra or not self.es_maduro:
            return []

        mes_real = mes % 12
        factor_reprod = 0.3 + 0.7 * np.exp(-0.5 * ((mes_real - 2) / 2.5)**2)
        factor_reprod += 0.3 + 0.7 * np.exp(-0.5 * ((mes_real - 9) / 2.5)**2)
        factor_reprod = min(1.0, factor_reprod / 2)

        temp_opt = 27.5
        factor_temp = np.exp(-0.1 * (temp - temp_opt)**2)
        factor_temp = max(0.3, factor_temp)

        factor_densidad = max(0.5, 1.0 - densidad_hembras / 8.0)

        prob_reprod = self.prob_reprod * factor_reprod * factor_temp * factor_densidad

        if np.random.rand() < prob_reprod:
            n_huevos = int(30 + 15 * (self.talla - 4.0) * factor_reprod)
            n_huevos = max(5, min(120, n_huevos))

            supervivencia = self.supervivencia_huevos * factor_temp * factor_densidad
            n_descendientes = int(n_huevos * supervivencia)
            n_descendientes = min(n_descendientes, 15)

            nuevos = []
            for _ in range(n_descendientes):
                talla_juvenil = np.random.normal(2.5, 0.5)
                talla_juvenil = max(1.5, min(3.5, talla_juvenil))
                cria = CangrejoCalibrado(self.morfo, params, habitat=self.habitat)
                cria.talla = talla_juvenil
                cria.es_hembra = np.random.rand() < 0.5
                cria.es_maduro = False
                cria.edad = 0
                nuevos.append(cria)

            return nuevos
        return []


