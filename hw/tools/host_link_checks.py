"""Independent physical-pin fixture, transcribed from TI PW/DCK/DBZ tables.

The application/JTAG switch permutation is checked at both ends. Power pins
and default bias resistors are included; a logical net name alone is insufficient.
"""
from hardware_require import require as _require_hardware
from collections import Counter

# Independent purchasing/package fixture: pin connectivity cannot detect a
# wrong reset polarity/threshold variant, a DNP bypass or a decade-value error.
PARTS = {
 'U100':('TMUX1574PWR','TMUX1574PWR','Package_SO__TSSOP-16_4.4x5mm_P0.65mm'),
 'U101':('TMUX1574PWR','TMUX1574PWR','Package_SO__TSSOP-16_4.4x5mm_P0.65mm'),
 'U102':('TCA9534PWR','TCA9534PWR','Package_SO__TSSOP-16_4.4x5mm_P0.65mm'),
 'U103':('SN74LVC1G10DCKR','SN74LVC1G10DCKR','Package_TO_SOT_SMD__SOT-363_SC-70-6'),
 'U104':('TLV809EA30DBZR','TLV809EA30DBZR','Package_TO_SOT_SMD__SOT-23'),
 'U105':('TLV809EA30DBZR','TLV809EA30DBZR','Package_TO_SOT_SMD__SOT-23'),
 'U106':('SN74LVC1G08DCKR','SN74LVC1G08DCKR','Package_TO_SOT_SMD__SOT-353_SC-70-5'),
}
for i in range(100,107):
    PARTS[f'C{i}']=('100n','GRM188R71H104KA93D','Capacitor_SMD__C_0603_1608Metric')
for i in range(100,119):
    value,mpn=('22','RC0603FR-0722RL') if i<106 else (
        ('100k','RC0603FR-07100KL') if i in (112,114,116,117) else ('10k','RC0603FR-0710KL'))
    PARTS[f'R{i}']=(value,mpn,'Resistor_SMD__R_0603_1608Metric')


def verify_parts(spec, bom, board):
    placement={row['ref']:row for row in spec['parts']}
    rows={row['Reference']:row for row in bom}
    _require_hardware((len(rows)==len(bom)), lambda: ('Duplicate BOM reference'))
    footprints={f.GetReference():f for f in board.GetFootprints()}
    for ref,(value,mpn,footprint) in PARTS.items():
        meta,row,physical=placement[ref],rows[ref],footprints[ref]
        _require_hardware(((meta['value'],meta['mpn'],meta['local_fp'])==(value,mpn,footprint)), lambda: (('Part variant',ref)))
        _require_hardware((meta['dnp'] is False), lambda: (('Required part marked DNP',ref)))
        _require_hardware(((row['Value'],row['MPN'],row['Footprint'])==(value,mpn,footprint)), lambda: (('BOM part',ref)))
        _require_hardware((row['DNP']=='False'), lambda: (('BOM DNP',ref)))
        _require_hardware((not physical.IsDNP()), lambda: (('PCB DNP',ref)))
        _require_hardware((physical.GetValue()==value), lambda: (('PCB value',ref)))
        _require_hardware((physical.GetFPID().GetLibItemName()==footprint), lambda: (('PCB package',ref)))
    return len(PARTS)

FIXTURE = {
 'J1':{12:'PI_LINK_CS_N',32:'PI_LINK_DQ3',35:'PI_LINK_DQ1',36:'PI_LINK_DQ2',
       38:'PI_LINK_DQ0',40:'PI_LINK_SCLK',8:'PI_UART_TX',10:'PI_UART_RX'},
 'J81':{21:'FPGA_LINK_SCLK',23:'FPGA_LINK_CS_N',22:'FPGA_LINK_DQ0',
        24:'FPGA_LINK_DQ1',26:'FPGA_LINK_DQ2',28:'FPGA_LINK_DQ3',
        94:'JTAG_TMS',96:'JTAG_TDI',98:'JTAG_TDO',100:'JTAG_TCK'},
 'U100':{1:'LINK_JTAG_SEL',2:'FPGA_LINK_SCLK',3:'JTAG_TCK',4:'LINK_SCLK',
         5:'FPGA_LINK_DQ0',6:'JTAG_TDI',7:'LINK_DQ0',8:'GND',9:'LINK_DQ1',
         10:'JTAG_TDO',11:'FPGA_LINK_DQ1',12:'LINK_DQ2',13:'JTAG_TMS',
         14:'FPGA_LINK_DQ2',15:'LINK_OE_N',16:'FPGA_3V3'},
 'U101':{1:'LINK_JTAG_SEL',2:'FPGA_LINK_CS_N',4:'LINK_CS_N',5:'FPGA_LINK_DQ3',
         7:'LINK_DQ3',8:'GND',9:'GND',10:'GND',11:'GND',12:'GND',13:'GND',
         14:'GND',15:'LINK_OE_N',16:'FPGA_3V3'},
 'U102':{1:'GND',2:'GND',3:'GND',4:'LINK_JTAG_SEL',5:'LINK_REQUEST',
         6:'GND',7:'GND',8:'GND',9:'GND',10:'GND',11:'GND',12:'GND',
         14:'PI_I2C_SCL',15:'PI_I2C_SDA',16:'PI_3V3'},
 'U103':{1:'LINK_ARMED_REQUEST',2:'GND',3:'LINK_PI_GOOD',4:'LINK_OE_N',
         5:'FPGA_3V3',6:'LINK_FPGA_GOOD'},
 'U104':{1:'GND',2:'LINK_PI_GOOD',3:'PI_3V3'},
 'U105':{1:'GND',2:'LINK_FPGA_GOOD',3:'FPGA_3V3'},
 'U106':{1:'LINK_REQUEST',2:'FPGA_IO_ENABLE',3:'GND',4:'LINK_ARMED_REQUEST',5:'FPGA_3V3'},
 'R106':{1:'LINK_JTAG_SEL',2:'GND'},'R107':{1:'LINK_REQUEST',2:'GND'},
 'R108':{1:'LINK_OE_N',2:'FPGA_3V3'},'R109':{1:'LINK_PI_GOOD',2:'GND'},
 'R110':{1:'LINK_FPGA_GOOD',2:'GND'},'R111':{1:'FPGA_LINK_CS_N',2:'FPGA_3V3'},
 'R112':{1:'FPGA_LINK_SCLK',2:'GND'},'R113':{1:'JTAG_TMS',2:'FPGA_3V3'},
 'R114':{1:'JTAG_TCK',2:'GND'},'R115':{1:'JTAG_TDI',2:'FPGA_3V3'},
 'R116':{1:'FPGA_LINK_DQ2',2:'GND'},'R117':{1:'FPGA_LINK_DQ3',2:'GND'},
 'R118':{1:'PI_UART_RX',2:'PI_3V3'},
}
for i, signal in enumerate(('SCLK','DQ0','DQ1','DQ2','CS_N','DQ3')):
    FIXTURE[f'R{100+i}']={1:'PI_LINK_'+signal,2:'LINK_'+signal}
for i in range(7):
    FIXTURE[f'C{100+i}']={1:'PI_3V3' if i in (2,4) else 'FPGA_3V3',2:'GND'}


def verify(pins):
    for ref, assignments in FIXTURE.items():
        for number, net in assignments.items():
            _require_hardware((pins.get((ref,str(number))) == net), lambda: ((ref,number,net,pins.get((ref,str(number))))))
    degree=Counter(pins.values())
    for key in [('U101','3'),('U101','6'),('U102','13')]:
        _require_hardware((pins[key] and degree[pins[key]] == 1), lambda: (('Parking/unused output must be open',key)))
    # Signals on opposite sides of the switches must not be shorted by bypasses.
    for signal in ('SCLK','DQ0','DQ1','DQ2','CS_N','DQ3'):
        net='PI_LINK_'+signal
        _require_hardware((degree[net] == 2), lambda: (('Pi line has unintended stub or bypass',net)))
    for net, switch_pin, module_pin, bias in [
        ('JTAG_TCK',3,100,('R114','1')),('JTAG_TDI',6,96,('R115','1')),
        ('JTAG_TDO',10,98,None),('JTAG_TMS',13,94,('R113','1'))]:
        expected={('U100',str(switch_pin)),('J81',str(module_pin))}
        if bias:expected.add(bias)
        _require_hardware(({key for key,value in pins.items() if value==net} == expected), lambda: (('JTAG bypass/stub',net)))
    return sum(map(len,FIXTURE.values())) + 13
