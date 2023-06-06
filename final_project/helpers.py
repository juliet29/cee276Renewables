import numpy as np
# import units as u
import numpy as np
import pandas as pd

import rasterio
from rasterio.plot import show_hist, show
import geopandas as gpd
import rasterstats
from shapely.geometry import shape

import plotly.graph_objects as go
from plotly.subplots import make_subplots
from matplotlib import pyplot as plt

from icecream import ic

def print_nice(float):
    return print(f"{float:,.0f}")

# conversions 
w_to_mw = 1/1e6
w_to_kw = 1/1e3
hours_per_year = 8760.0
w_to_wh = hours_per_year

kw_to_w = 1/w_to_kw
wh_to_w = 1/w_to_wh


def calculate_power_panel(F_cur, T_a, w):
    """
    F_cur = _ # W/m^2 current solar flux normal to the panel 
    T_a = _ # K / ºC, air temperature the panel is exposed to 
    w = _ # m/s, wind speed panel is exposed to 
    => all of these are arrays 

    return power potential of a single panel in the area defined by the characteristics above
    
    """
    F_cur = F_cur  * kw_to_w # TODO comes in with kwh/m2 strange, just converting to "wh", not sure of the timing ...
    # values that change based on design! 
    D_f = 0.864 # derating factor, product of correction factors for additional processes affecting solar output, Table 5.2 
    E_panel = 0.18 # solar panel efficiency obtained under standard test conditions -- Ex 5.2
    A_panel = 1.5 # m^2, surface area of the pane -- Ex 5.2
    
    # 5.9, cell temperature, empirical so units do not eqate 
    T_c = T_a + 0.32 * (F_cur/(8.91 + 2*w))

    b_ref = 0.0025 # / K, temperature coefficient 
    T_th = 55 # K, threshold temeprature 
    T_ref = 298.15 # K, reference temperature 
    # 5.8, correction for cell temperature 
    C_temp = 1 - b_ref * np.maximum( np.minimum(T_c - T_ref, T_th ), 0 )

    # 5.7 actual AC power output from a solar panel at a given time 
    # P_ac = p_mpp_stc * C_temp * D_f / F_1000 # W based on panel rating
    P_ac = F_cur * A_panel * E_panel * C_temp * D_f # W, based on real conditions 

    # TODO panels arent rated, unclear? given volts etc...


    return P_ac


def calc_num_panels(p_land, num_states, state_areas, P_ac):

    # want to use land in states that are most productive
    state_energy_sort = P_ac.sort_values(ascending=False)
    # ic(len(P_ac))
    # ic(num_states)
    state_energy_lim = state_energy_sort[0:int(num_states)]

    # land available to use is a percent of the total land in the state 
    land_avail = state_areas.iloc[state_energy_lim.index]["area (m2)"].apply(lambda x: x*p_land)

    # calc number of solar panels on this land, assuming standard panels 
    A_panel = 1.5 # m2
    n_panels = np.round(land_avail/A_panel)

    # installed_power = P_mpp * n_panels TODO: think this should be some function of the array layout...

    true_power = n_panels * P_ac

    total_energy = true_power.sum()*w_to_mw*w_to_wh

    return {
        "n_panels": n_panels.dropna(),
        # "installed_power": installed_power.dropna(),
        "true_power": true_power.dropna(),
        # "capacity_factors": true_power.dropna()/installed_power.dropna(),
        "total_energy (mwh)": total_energy,
        
    }


def calculate_power_turbine(V_m):
    """
    V_m : mean wind speed # m/s # mean wind speed, will get this from a data source for different areas.
    """

    ## --- atmosphereic values # TODO get real values 
    rho = 1.23 # kg/m^3 # air density, should be a function of turbine height 

    ## ---  turbine details #TODO find realistic value 
    # source: https://www.energy.gov/eere/articles/wind-turbines-bigger-better
    D_t = 127 # m 


    # 6.7, the swept area of a wind turbine 
    A_t = np.pi * D_t**2 / 4

    # 6.11, assuming a Rayleigh distribution of wind speeds, the mean power available in the wind is P_m 
    # P_m = 1/2 * rho * A_t * np.sum(f(v) * v**3 )
    P_m = (6/np.pi) * (0.5) * rho * A_t * V_m**3 # W

    # choose turbines that are rated higher than the power available in the wind 
    # has to be in kilowatts for generalized capacity factor equation 
    P_r = np.ceil(P_m/ 500) * 500
    

    # 6.28, generalized capacity factor equation 
    CF = 0.087 * V_m - ((P_r * w_to_kw)/(D_t**2))

    # 6.24, gross annual energy output and power output 
    H = 8760 # non leap year hours in  a day 
    P_t = P_r * CF 
    E_t = P_t * H 

    # account for losses 
    L_td = 16.1 # tranmission and distribution loss, Table 6.3
    L_d = 1.6 # downtime losses, Section 6.6.6.2 ~ Faultstich et al 2011 
    L_c = 0 # curtailment losses, assume storage is available 
    L_a = 0.2 # array losses, # Figure 6.25b, Jacobson and Archer TODO model array losses as function of density... 
    pL_td = 1 - L_td/100 
    pL_d = 1 - L_td/100 
    pL_c = 1 - L_c/100
    pL_a = 1 - L_a/100 
    L_t = (1 - (pL_td * pL_d * pL_c * pL_a )) # compound losses 

    P_t_after_losses = P_t * (1 - L_t)


    return P_m, P_t, CF, P_t_after_losses, P_r


def calc_num_turbines(p_land, num_states, state_areas, P_t_after_losses, P_r):

    # want to use land in states that are most productive
    state_energy_sort = P_t_after_losses.sort_values(ascending=False)
    state_energy_lim = state_energy_sort[0:int(num_states)]

    # land available to use is a percent of the total land in the state 
    land_avail = state_areas.iloc[state_energy_lim.index]["area (m2)"].apply(lambda x: x*p_land)

    # determine the number of turbines that can fit on land using rated power 
    installed_power_density = 19.8 # mw/km2 => w/m2, # W/m2 Table 6.4, mean output power density of onshore europe turbines
    # TODO see Enevoldsen and Jacobson 2020 to see how array losses compared with density for L_a above 

    n_turbines = np.round(installed_power_density / P_r * land_avail )

    installed_power = n_turbines * P_r 

    true_power = n_turbines * P_t_after_losses

    total_energy = true_power.sum()*w_to_mw*w_to_wh


    return {
        "n_turbines": n_turbines.dropna(),
        "installed_power": installed_power.dropna(),
        "true_power": true_power.dropna(),
        "capacity_factors": true_power.dropna()/installed_power.dropna(),
        "total_energy (mwh)": total_energy,
        
    }