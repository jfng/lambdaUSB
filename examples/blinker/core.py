from nmigen import *

from lambdausb.cfg import ConfigurationEndpoint
from lambdausb.dev import USBDevice
from lambdausb.lib import stream
# from lambdausb.phy.ulpi import ULPIPhy
from lambdausb.phy.usb import USBPHY
from lambdausb.phy.rs232 import RS232PHY
from lambdausb.protocol import Transfer


class RgbBlinkerEndpoint(Elaboratable):
    def __init__(self, rgb_led):
        self.rgb_led = rgb_led
        self.sink = stream.Endpoint([("data", 8)])

    def elaborate(self, platform):
        m = Module()

        led = Signal()
        sel = Record([("r", 1), ("g", 1), ("b", 1)])

        m.d.comb += self.sink.ready.eq(Const(1))
        with m.If(self.sink.valid):
            m.d.sync += sel.eq(self.sink.data[:3])

        clk_freq = platform.default_clk_frequency
        ctr = Signal(range(int(clk_freq//2)), reset=int(clk_freq//2)-1)
        with m.If(ctr == 0):
            m.d.sync += ctr.eq(ctr.reset)
            m.d.sync += led.eq(~led)
        with m.Else():
            m.d.sync += ctr.eq(ctr - 1)

        m.d.comb += [
            self.rgb_led.r.o.eq(sel.r & led),
            self.rgb_led.g.o.eq(sel.g & led),
            self.rgb_led.b.o.eq(sel.b & led)
        ]

        return m


class USBBlinker(Elaboratable):
    def elaborate(self, platform):
        m = Module()

        # # USB device
        # ulpi_phy = m.submodules.ulpi_phy = ULPIPhy(platform.request("ulpi", 0))
        # usb_dev  = m.submodules.usb_dev  = USBDevice(ulpi_phy)

        cd_sync = m.domains.cd_sync = ClockDomain("sync")
        platform.add_clock_constraint(cd_sync.clk, 48e6)

        m.submodules += Instance("SB_PLL40_PAD",
            p_FEEDBACK_PATH="SIMPLE",
            p_PLLOUT_SELECT="GENCLK",
            p_DIVR=0, p_DIVF=63, p_DIVQ=4,
            p_FILTER_RANGE=6,
            i_PACKAGEPIN=platform.request("clk12", 0, dir="-"),
            o_PLLOUTGLOBAL=ClockSignal("sync"),
            i_RESETB=Const(1), i_BYPASS=Const(0),
        )

        usb_pins = platform.request("usb", 0, xdr={"p": 1, "n": 1})
        for pin in usb_pins.p, usb_pins.n:
            m.d.comb += [
                pin.i_clk.eq(ClockSignal("sync")),
                pin.o_clk.eq(ClockSignal("sync"))
            ]

        usb_phy = m.submodules.usb_phy = USBPHY(usb_pins, 48e6)
        usb_dev = m.submodules.usb_dev = USBDevice(usb_phy)

        # Configuration endpoint
        from config import descriptor_map, rom_init
        cfg_ep  = m.submodules.cfg_ep = ConfigurationEndpoint(descriptor_map, rom_init)
        cfg_in  = usb_dev.input_port(0x0, 64, Transfer.CONTROL)
        cfg_out = usb_dev.output_port(0x0, 64, Transfer.CONTROL)

        m.d.comb += [
            cfg_ep.source.connect(cfg_in),
            cfg_out.connect(cfg_ep.sink)
        ]

        # RGB blinker endpoint
        rgb_ep  = m.submodules.rgb_ep = RgbBlinkerEndpoint(platform.request("rgb_led", 0))
        rgb_out = usb_dev.output_port(0x1, 512, Transfer.BULK)

        m.d.comb += rgb_out.connect(rgb_ep.sink)

        return m


if __name__ == "__main__":
    # from lambdausb.boards.usbsniffer import USBSnifferPlatform
    # platform = USBSnifferPlatform()

    # from nmigen_boards.arty_a7 import ArtyA7Platform
    from nmigen_boards.ice40_up5k_b_evn import ICE40UP5KBEVNPlatform
    from nmigen.build.dsl import *
    platform = ICE40UP5KBEVNPlatform()
    platform.add_resources([
        # Resource("ulpi", 0,
        #     Subsignal("clk", Pins("1", conn=("pmod", 3), dir="i"), Clock(60e6)),
        #     Subsignal("dir", Pins("9", conn=("pmod", 2), dir="i")),
        #     Subsignal("nxt", Pins("8", conn=("pmod", 2), dir="i")),
        #     Subsignal("stp", Pins("7", conn=("pmod", 2), dir="o")),
        #     Subsignal("rst", Pins("8", conn=("pmod", 3), dir="o")),
        #     # Subsignal("data", Pins("4 10 3 9", conn=("pmod", 3), dir="io"), Pins("4 3 2 1", conn=("pmod", 2), dir="io")),
        #     Subsignal("data", Pins("F3 G2 F4 H2 V11 V10 V12 U12", dir="io")),
        #     Subsignal("data_lo", Pins("4 10 3 9", conn=("pmod", 3), dir="io")),
        #     Subsignal("data_hi", Pins("4  3 2 1", conn=("pmod", 2), dir="io")),
        #     Attrs(IOSTANDARD="LVCMOS33", SLEW="FAST")
        # ),
        # Resource("ulpi", 1,
        #     Subsignal("clk", Pins("1", conn=("pmod", 1), dir="i"), Clock(60e6)),
        #     Subsignal("dir", Pins("2", conn=("pmod", 1), dir="i")),
        #     Subsignal("nxt", Pins("3", conn=("pmod", 1), dir="i")),
        #     Subsignal("stp", Pins("4", conn=("pmod", 1), dir="o")),
        #     Subsignal("rst", Pins("10", conn=("pmod", 1), dir="o")),
        #     Subsignal("data", Pins("7 8 9 10 1 2 3 4", conn=("pmod", 2), dir="io")),
        #     Attrs(IOSTANDARD="LVCMOS33", SLEW="FAST")
        # ),
        Resource("usb", 0,
            # Subsignal("p", Pins("1", conn=("pmod", 1), dir="io"), Attrs(PULLUP="TRUE")),
            Subsignal("p", Pins("10", conn=("j", 2), dir="io")),
            Subsignal("n", Pins("12", conn=("j", 2), dir="io")),
            # Attrs(IOSTANDARD="LVCMOS33")
            Attrs(IO_STANDARD="LVCMOS33")
        ),
        Resource("debug", 1,
            Subsignal("_0", Pins(" 7", conn=("j", 2), dir="o")),
            Subsignal("_1", Pins(" 9", conn=("j", 2), dir="o")),
            Subsignal("_2", Pins("11", conn=("j", 2), dir="o")),
            Subsignal("_3", Pins("13", conn=("j", 2), dir="o")),
            Subsignal("_4", Pins("15", conn=("j", 2), dir="o")),
            Attrs(IO_STANDARD="LVCMOS33")
        ),
        # Resource("usb", 1,
        #     Subsignal("p", Pins("1", conn=("pmod", 2), dir="io"), Attrs(PULLUP="TRUE")),
        #     Subsignal("n", Pins("2", conn=("pmod", 2), dir="io")),
        #     Attrs(IOSTANDARD="LVCMOS33")
        # ),
        # Resource("debug", 0,
        #     Subsignal("_0", Pins("3", conn=("pmod", 2), dir="o")),
        #     Subsignal("_1", Pins("4", conn=("pmod", 2), dir="o")),
        #     Subsignal("_2", Pins("7", conn=("pmod", 2), dir="o")),
        #     Subsignal("_3", Pins("8", conn=("pmod", 2), dir="o")),
        #     Subsignal("_4", Pins("9", conn=("pmod", 2), dir="o")),
        #     Subsignal("_5", Pins("10", conn=("pmod", 2), dir="o")),
        #     Subsignal("_6", Pins("1", conn=("pmod", 2), dir="o")),
        #     Subsignal("_7", Pins("2", conn=("pmod", 2), dir="o")),
        #     Subsignal("_8", Pins("7", conn=("pmod", 1), dir="o")),
        #     Subsignal("_9", Pins("8", conn=("pmod", 1), dir="o")),
        #     Attrs(IOSTANDARD="LVCMOS33")
        # )
    ])
    platform.build(USBBlinker(), do_program=True)
