from pint import UnitRegistry


ureg = UnitRegistry()
ureg.default_format = '.3f'
Q_ = ureg.Quantity

# time 
s = ureg.second
hour = ureg.hour
day = ureg.day
year = ureg.year

# distance 
m = ureg.meter 

# mass
g = ureg.gram
kg = ureg.kilogram

# force
newton = ureg.newton

# energy and power
mj = ureg.megajoule
j = ureg.joule
kwh = ureg.kilowatt*ureg.hour
mwh = ureg.megawatt*ureg.hour


watt = ureg.watt
megawatt = ureg.megawatt

# electricity 
ohm = ureg.ohm 
amp = ureg.ampere
volt = ureg.volt

# temperature 
natural_temp = Q_(15, ureg.degC)


# currency 
ureg.define('USD = currency')
USD = ureg.USD
