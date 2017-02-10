# 1:4 frequency-ratio DDR3 PHYs for KintexUltrascale
# tCK=5ns CL=7 CWL=6

from litex.gen import *

from litex.soc.interconnect.csr import *

from litedram.common import PhySettings
from litedram.phy.dfi import *
from litedram.phy.bitslip import BitSlip

# TODO:
# - verify read_latency in simulation (OSERDESE3/ISERDESE3)
# - verify initial p_DELAY_VALUE on ODELAYE3/IDELAYE3
# - simulate with Micron's model
# - test on board

class KUSDDRPHY(Module, AutoCSR):
    def __init__(self, pads):
        addressbits = len(pads.a)
        bankbits = len(pads.ba)
        databits = len(pads.dq)
        nphases = 4

        self._wlevel_en = CSRStorage()
        self._wlevel_strobe = CSR()
        self._dly_sel = CSRStorage(databits//8)
        self._rdly_dq_rst = CSR()
        self._rdly_dq_inc = CSR()
        self._rdly_dq_bitslip = CSRStorage(3)
        self._wdly_dq_rst = CSR()
        self._wdly_dq_inc = CSR()
        self._wdly_dqs_rst = CSR()
        self._wdly_dqs_inc = CSR()

        self.settings = PhySettings(
            memtype="DDR3",
            dfi_databits=2*databits,
            nphases=nphases,
            rdphase=0,
            wrphase=2,
            rdcmdphase=1,
            wrcmdphase=0,
            cl=7,
            cwl=6,
            read_latency=8,
            write_latency=2
        )

        self.dfi = Interface(addressbits, bankbits, 2*databits, nphases)

        # # #

        # Clock
        sd_clk_se = Signal()
        self.specials += [
            Instance("OSERDESE3",
                p_DATA_WIDTH=8, p_INIT=0,
                p_IS_CLK_INVERTED=0, p_IS_CLKDIV_INVERTED=0, p_IS_RST_INVERTED=0,

                o_OQ=sd_clk_se,
                i_RST=ResetSignal(),
                i_CLK=ClockSignal("sys4x"), i_CLKDIV=ClockSignal(),
                i_D1=0, i_D2=1, i_D3=0, i_D4=1,
                i_D5=0, i_D6=1, i_D7=0, i_D8=1
            ),
            Instance("OBUFDS",
                i_I=sd_clk_se,
                o_O=pads.clk_p,
                o_OB=pads.clk_n
            )
        ]

        # Addresses and commands
        for i in range(addressbits):
            self.specials += \
                Instance("OSERDESE3",
                    p_DATA_WIDTH=8, p_INIT=0,
                    p_IS_CLK_INVERTED=0, p_IS_CLKDIV_INVERTED=0, p_IS_RST_INVERTED=0,

                    o_OQ=pads.a[i],
                    i_RST=ResetSignal(),
                    i_CLK=ClockSignal("sys4x"), i_CLKDIV=ClockSignal(),
                    i_D1=self.dfi.phases[0].address[i], i_D2=self.dfi.phases[0].address[i],
                    i_D3=self.dfi.phases[1].address[i], i_D4=self.dfi.phases[1].address[i],
                    i_D5=self.dfi.phases[2].address[i], i_D6=self.dfi.phases[2].address[i],
                    i_D7=self.dfi.phases[3].address[i], i_D8=self.dfi.phases[3].address[i]
                )
        for i in range(bankbits):
            self.specials += \
                Instance("OSERDESE3",
                    p_DATA_WIDTH=8, p_INIT=0,
                    p_IS_CLK_INVERTED=0, p_IS_CLKDIV_INVERTED=0, p_IS_RST_INVERTED=0,

                    o_OQ=pads.ba[i],
                    i_RST=ResetSignal(),
                    i_CLK=ClockSignal("sys4x"), i_CLKDIV=ClockSignal(),
                    i_D1=self.dfi.phases[0].bank[i], i_D2=self.dfi.phases[0].bank[i],
                    i_D3=self.dfi.phases[1].bank[i], i_D4=self.dfi.phases[1].bank[i],
                    i_D5=self.dfi.phases[2].bank[i], i_D6=self.dfi.phases[2].bank[i],
                    i_D7=self.dfi.phases[3].bank[i], i_D8=self.dfi.phases[3].bank[i]
                )
        for name in "ras_n", "cas_n", "we_n", "cs_n", "cke", "odt", "reset_n":
            self.specials += \
                Instance("OSERDESE3",
                    p_DATA_WIDTH=8, p_INIT=0,
                    p_IS_CLK_INVERTED=0, p_IS_CLKDIV_INVERTED=0, p_IS_RST_INVERTED=0,

                    o_OQ=getattr(pads, name),
                    i_RST=ResetSignal(),
                    i_CLK=ClockSignal("sys4x"), i_CLKDIV=ClockSignal(),
                    i_D1=getattr(self.dfi.phases[0], name), i_D2=getattr(self.dfi.phases[0], name),
                    i_D3=getattr(self.dfi.phases[1], name), i_D4=getattr(self.dfi.phases[1], name),
                    i_D5=getattr(self.dfi.phases[2], name), i_D6=getattr(self.dfi.phases[2], name),
                    i_D7=getattr(self.dfi.phases[3], name), i_D8=getattr(self.dfi.phases[3], name)
                )

        # DQS and DM
        oe_dqs = Signal()
        dqs_serdes_pattern = Signal(8)
        self.comb += \
            If(self._wlevel_en.storage,
                If(self._wlevel_strobe.re,
                    dqs_serdes_pattern.eq(0b00000001)
                ).Else(
                    dqs_serdes_pattern.eq(0b00000000)
                )
            ).Else(
                dqs_serdes_pattern.eq(0b01010101)
            )
        for i in range(databits//8):
            dm_o_nodelay = Signal()
            self.specials += \
                Instance("OSERDESE3",
                    p_DATA_WIDTH=8, p_INIT=0,
                    p_IS_CLK_INVERTED=0, p_IS_CLKDIV_INVERTED=0, p_IS_RST_INVERTED=0,

                    o_OQ=dm_o_nodelay,
                    i_RST=ResetSignal(),
                    i_CLK=ClockSignal("sys4x"), i_CLKDIV=ClockSignal(),
                    i_D1=self.dfi.phases[0].wrdata_mask[i], i_D2=self.dfi.phases[0].wrdata_mask[databits//8+i],
                    i_D3=self.dfi.phases[1].wrdata_mask[i], i_D4=self.dfi.phases[1].wrdata_mask[databits//8+i],
                    i_D5=self.dfi.phases[2].wrdata_mask[i], i_D6=self.dfi.phases[2].wrdata_mask[databits//8+i],
                    i_D7=self.dfi.phases[3].wrdata_mask[i], i_D8=self.dfi.phases[3].wrdata_mask[databits//8+i]
                )
            self.specials += \
                Instance("ODELAYE3",
                    p_CASCADE="NONE", p_UPDATE_MODE="ASYNC", p_REFCLK_FREQUENCY=200.0,
                    p_IS_CLK_INVERTED=0, p_IS_RST_INVERTED=0,
                    p_DELAY_FORMAT="COUNT", p_DELAY_TYPE="VARIABLE", p_DELAY_VALUE=0,

                    i_CLK=ClockSignal(),
                    i_INC=1, i_EN_VTC=1,
                    i_LOAD=self._dly_sel.storage[i] & self._wdly_dq_rst.re,
                    i_CE=self._dly_sel.storage[i] & self._wdly_dq_inc.re,

                    o_ODATAIN=dm_o_nodelay, o_DATAOUT=pads.dm[i]
                )

            dqs_nodelay = Signal()
            dqs_delayed = Signal()
            dqs_t = Signal()
            self.specials += [
                Instance("OSERDESE3",
                    p_DATA_WIDTH=8, p_INIT=0,
                    p_IS_CLK_INVERTED=0, p_IS_CLKDIV_INVERTED=0, p_IS_RST_INVERTED=0,

                    o_OQ=dqs_nodelay, o_T_OUT=dqs_t,
                    i_RST=ResetSignal(),
                    i_CLK=ClockSignal("sys4x"), i_CLKDIV=ClockSignal(),
                    i_D1=dqs_serdes_pattern[0], i_D2=dqs_serdes_pattern[1],
                    i_D3=dqs_serdes_pattern[2], i_D4=dqs_serdes_pattern[3],
                    i_D5=dqs_serdes_pattern[4], i_D6=dqs_serdes_pattern[5],
                    i_D7=dqs_serdes_pattern[6], i_D8=dqs_serdes_pattern[7],
                    i_T=~oe_dqs,
                ),
                Instance("ODELAYE3",
                    p_CASCADE="NONE", p_UPDATE_MODE="ASYNC", p_REFCLK_FREQUENCY=200.0,
                    p_IS_CLK_INVERTED=0, p_IS_RST_INVERTED=0,
                    p_DELAY_FORMAT="COUNT", p_DELAY_TYPE="VARIABLE", p_DELAY_VALUE=6, # TODO: verify value

                    i_CLK=ClockSignal(),
                    i_INC=1, i_EN_VTC=1,
                    i_LOAD=self._dly_sel.storage[i] & self._wdly_dqs_rst.re,
                    i_CE=self._dly_sel.storage[i] & self._wdly_dqs_inc.re,

                    o_ODATAIN=dqs_nodelay, o_DATAOUT=dqs_delayed
                ),
                Instance("OBUFTDS",
                    i_I=dqs_delayed, i_T=dqs_t,
                    o_O=pads.dqs_p[i], o_OB=pads.dqs_n[i]
                )
            ]

        # DQ
        oe_dq = Signal()
        for i in range(databits):
            dq_o_nodelay = Signal()
            dq_o_delayed = Signal()
            dq_i_nodelay = Signal()
            dq_i_delayed = Signal()
            dq_t = Signal()
            dq_bitslip = BitSlip(8)
            self.sync += \
                If(self._dly_sel.storage[i//8],
                    dq_bitslip.value.eq(self._rdly_dq_bitslip.storage)
                )
            self.submodules += dq_bitslip
            self.specials += [
                Instance("OSERDESE3",
                    p_DATA_WIDTH=8, p_INIT=0,
                    p_IS_CLK_INVERTED=0, p_IS_CLKDIV_INVERTED=0, p_IS_RST_INVERTED=0,

                    o_OQ=dq_o_nodelay, o_T_OUT=dq_t,
                    i_RST=ResetSignal(),
                    i_CLK=ClockSignal("sys4x"), i_CLKDIV=ClockSignal(),
                    i_D1=self.dfi.phases[0].wrdata[i], i_D2=self.dfi.phases[0].wrdata[databits+i],
                    i_D3=self.dfi.phases[1].wrdata[i], i_D4=self.dfi.phases[1].wrdata[databits+i],
                    i_D5=self.dfi.phases[2].wrdata[i], i_D6=self.dfi.phases[2].wrdata[databits+i],
                    i_D7=self.dfi.phases[3].wrdata[i], i_D8=self.dfi.phases[3].wrdata[databits+i],
                    i_T=~oe_dq
                ),
                Instance("ISERDESE3",
                    p_DATA_WIDTH=8,

                    i_D=dq_i_delayed,
                    i_RST=ResetSignal(),
                    i_FIFO_RD_CLK=0, i_FIFO_RD_EN=0,
                    i_CLK=ClockSignal("sys4x"), i_CLKB=~ClockSignal("sys4x"), i_CLKDIV=ClockSignal(),
                    o_Q8=dq_bitslip.i[7], o_Q7=dq_bitslip.i[6],
                    o_Q6=dq_bitslip.i[5], o_Q5=dq_bitslip.i[4],
                    o_Q4=dq_bitslip.i[3], o_Q3=dq_bitslip.i[2],
                    o_Q2=dq_bitslip.i[1], o_Q1=dq_bitslip.i[0]
                ),
                Instance("ODELAYE3",
                    p_CASCADE="NONE", p_UPDATE_MODE="ASYNC", p_REFCLK_FREQUENCY=200.0,
                    p_IS_CLK_INVERTED=0, p_IS_RST_INVERTED=0,
                    p_DELAY_FORMAT="COUNT", p_DELAY_TYPE="VARIABLE", p_DELAY_VALUE=6, # TODO: verify value

                    i_CLK=ClockSignal(),
                    i_INC=1, i_EN_VTC=1,
                    i_LOAD=self._dly_sel.storage[i//8] & self._wdly_dq_rst.re,
                    i_CE=self._dly_sel.storage[i//8] & self._wdly_dq_inc.re,

                    o_ODATAIN=dq_o_nodelay, o_DATAOUT=dq_o_delayed
                ),
                Instance("IDELAYE3",
                    p_CASCADE="NONE", p_UPDATE_MODE="ASYNC",p_REFCLK_FREQUENCY=200.0,
                    p_IS_CLK_INVERTED=0, p_IS_RST_INVERTED=0,
                    p_DELAY_FORMAT="COUNT", p_DELAY_SRC="IDATAIN",
                    p_DELAY_TYPE="VARIABLE", p_DELAY_VALUE=6, # TODO: verify value

                    i_CLK=ClockSignal(),
                    i_INC=1, i_EN_VTC=1,
                    i_LOAD=self._dly_sel.storage[i//8] & self._rdly_dq_rst.re,
                    i_CE=self._dly_sel.storage[i//8] & self._rdly_dq_inc.re,

                    i_IDATAIN=dq_i_nodelay, o_DATAOUT=dq_i_delayed
                ),
                Instance("IOBUF",
                    i_I=dq_o_delayed, o_O=dq_i_nodelay, i_T=dq_t,
                    io_IO=pads.dq[i]
                )
            ]
            self.comb += [
                self.dfi.phases[0].rddata[i].eq(dq_bitslip.o[7]),
                self.dfi.phases[1].rddata[i].eq(dq_bitslip.o[5]),
                self.dfi.phases[2].rddata[i].eq(dq_bitslip.o[3]),
                self.dfi.phases[3].rddata[i].eq(dq_bitslip.o[1]),

                self.dfi.phases[0].rddata[databits+i].eq(dq_bitslip.o[6]),
                self.dfi.phases[1].rddata[databits+i].eq(dq_bitslip.o[4]),
                self.dfi.phases[2].rddata[databits+i].eq(dq_bitslip.o[2]),
                self.dfi.phases[3].rddata[databits+i].eq(dq_bitslip.o[0]),
            ]

        # Flow control
        #
        # total read latency = 8:
        #  2 cycles through OSERDESE3 TODO: verify latency
        #  2 cycles CAS
        #  2 cycles through ISERDESE3 TODO: verify latency
        #  2 cycles through BitSlip
        rddata_en = self.dfi.phases[self.settings.rdphase].rddata_en
        for i in range(8-1):
            n_rddata_en = Signal()
            self.sync += n_rddata_en.eq(rddata_en)
            rddata_en = n_rddata_en
        self.sync += [phase.rddata_valid.eq(rddata_en | self._wlevel_en.storage)
            for phase in self.dfi.phases]

        oe = Signal()
        last_wrdata_en = Signal(4)
        wrphase = self.dfi.phases[self.settings.wrphase]
        self.sync += last_wrdata_en.eq(Cat(wrphase.wrdata_en, last_wrdata_en[:3]))
        self.comb += oe.eq(last_wrdata_en[1] | last_wrdata_en[2] | last_wrdata_en[3])
        self.sync += \
            If(self._wlevel_en.storage,
                oe_dqs.eq(1), oe_dq.eq(0)
            ).Else(
                oe_dqs.eq(oe), oe_dq.eq(oe)
            )
