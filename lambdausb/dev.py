from nmigen import *

from .ctl import DeviceController
from .mux import InputMultiplexer, OutputMultiplexer # FIXME


__all__ = ["USBDevice"]


class Device(Elaboratable):
    def __init__(self):
        self.rx = Record([
            ("stb",  1, DIR_FANIN),
            ("lst",  1, DIR_FANIN),
            ("data", 8, DIR_FANIN),
            ("rdy",  1, DIR_FANOUT),
        ])
        self.tx = Record([
            ("stb",  1, DIR_FANOUT),
            ("lst",  1, DIR_FANOUT),
            ("data", 8, DIR_FANOUT),
            ("rdy",  1, DIR_FANIN),
        ])

        self._i_mux  = InputMultiplexer()
        self._o_mux  = OutputMultiplexer()

    def add_endpoint(self, endpoint):
        if isinstance(endpoint, InputEndpoint):
            self._i_mux.add_endpoint(endpoint)
        elif isinstance(endpoint, OutputEndpoint):
            self._o_mux.add_endpoint(endpoint)
        else:
            raise ValueError("Invalid endpoint '{!r}'; must be either an InputEndpoint or an "
                             "OutputEndpoint".format(endpoint))

    def elaborate(self, platform):
        m = Module()

        ctl   = m.submodules.ctl   = DeviceController()
        i_mux = m.submodules.i_mux = self._i_mux
        o_mux = m.submodules.o_mux = self._o_mux

        m.d.comb += [
            ctl.rx_stb   .eq(self.rx.stb),
            ctl.rx_lst   .eq(self.rx.lst),
            ctl.rx_data  .eq(self.rx.data),
            self.rx.rdy  .eq(ctl.rx_rdy),

            self.tx.stb  .eq(ctl.tx_stb),
            self.tx.lst  .eq(ctl.tx_lst),
            self.tx.data .eq(ctl.tx_data),
            ctl.tx_rdy   .eq(self.tx.rdy),

            i_mux.ep_addr.eq(ctl.i_ep_addr),
            i_mux.ep_stb .eq(ctl.i_ep_stb),
            ctl.i_ep_rdy .eq(i_mux.ep_rdy),
            ctl.i_ep_xfer.eq(i_mux.ep_xfer),

            ctl.i_stb    .eq(i_mux.r_stb),
            ctl.i_lst    .eq(i_mux.r_lst),
            ctl.i_data   .eq(i_mux.r_data),
            ctl.i_zlp    .eq(i_mux.r_zlp),
            i_mux.r_rdy  .eq(ctl.i_rdy),
            i_mux.r_ack  .eq(ctl.i_ack),

            o_mux.ep_addr.eq(ctl.o_ep_addr),
            o_mux.ep_stb .eq(ctl.o_ep_stb),
            ctl.o_ep_rdy .eq(o_mux.ep_rdy),
            ctl.o_ep_xfer.eq(o_mux.ep_xfer),

            o_mux.w_stb  .eq(ctl.o_stb),
            o_mux.w_lst  .eq(ctl.o_lst),
            o_mux.w_data .eq(ctl.o_data),
            o_mux.w_setup.eq(ctl.o_setup),
            o_mux.w_drop .eq(ctl.o_drop),
            ctl.o_rdy    .eq(o_mux.w_rdy),

            i_mux.sof    .eq(ctl.sof),
            o_mux.sof    .eq(ctl.sof),
        ]

        return m
