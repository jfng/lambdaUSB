import os
import subprocess

from nmigen.build import *
from nmigen.vendor.lattice_ice40 import *
from .resources import *


__all__ = ["ICE40UP5KBEVNPlatform"]


class ICE40UP5KBEVNPlatform(LatticeICE40Platform):
    device      = "iCE40UP5K"
    package     = "SG48"
    default_clk = "clk12"
    resources   = [
        Resource("clk12", 0, Pins("35", dir="i"),
                 Clock(12e6), Attrs(GLOBAL=True, IO_STANDARD="LVCMOS33")),

        RGBLEDResource(0,
            r="41", g="40", b="39", invert=True,
            attrs=Attrs(IO_STANDARD="LVCMOS33")
        ),

        *SwitchResources(
            pins="23 25 34 43",
            attrs=Attrs(IO_STANDARD="LVCMOS33")
        ),

        UARTResource(0,
            # rx="25", tx="23",
            rx="36", tx="42",
            attrs=Attrs(IO_STANDARD="LVCMOS33")
        ),

        *SPIFlashResources(0,
            cs="16", clk="15", mosi="14", miso="17",
            attrs=Attrs(IO_STANDARD="LVCMOS33")
        ),
    ]
    connectors  = [
        Connector("j", 2, # J2
            "-  -  "
            "23 -  "
            "25 -  "
            "26 36 "
            "27 42 "
            "32 38 "
            "31 28 "
            "37 35 " # 35 is clk12
            "34 -  "
            "43 -  "),
        # TODO
        # Connector("j", 3, # J3
        # ),
        # Connector("j", 52, # J52
        # ),
        # Connector("pmod", 0, # U6
        # ),
    ]

    def toolchain_program(self, products, name):
        iceprog = os.environ.get("ICEPROG", "iceprog")
        with products.extract("{}.bin".format(name)) as bitstream_filename:
            subprocess.check_call([iceprog, "-S", bitstream_filename])


if __name__ == "__main__":
    from .test.blinky import *
    ICE40UP5KBEVNPlatform().build(Blinky(), do_program=True)
