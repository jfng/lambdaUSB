from collections import OrderedDict

from nmigen import *

from .lib import stream
from .ctl import USBController
# from .buf import USBOutputBuffer, USBInputBuffer, USBOutputMultiplexer # FIXME
from .buf import USBInputBuffer, USBOutputMultiplexer # FIXME
from .conn import USBOutputArbiter, USBInputArbiter
from .protocol import Transfer

__all__ = ["USBDevice"]


class USBDevice(Elaboratable):
    def __init__(self, phy):
        self.phy         = phy
        # self._input_map  = OrderedDict()
        # self._output_map = OrderedDict()

        self.sof = Signal()

        self._input_mux = USBInputMultiplexer()
        self.add_input_port = self.  _input_mux.add_endpoint # FIXME

        self._output_mux = USBOutputMultiplexer()
        self.add_output_port = self._output_mux.add_endpoint # FIXME

#     def input_port(self, ep_addr, max_size, xfer_type):
#         if not isinstance(ep_addr, int) or not ep_addr in range(0, 16):
#             raise TypeError("Endpoint address must be an integer in [0..16), not '{!r}'"
#                             .format(ep_addr))
#         if ep_addr in self._input_map:
#             raise ValueError("An input port for endpoint {} has already been requested"
#                              .format(ep_addr))
#         if not isinstance(xfer_type, Transfer):
#             raise TypeError("Transfer type must be a member of the Transfer enum, not '{!r}'"
#                             .format(xfer_type))

#         if xfer_type == Transfer.ISOCHRONOUS:
#             size_limit = 1024 # FIXME in FS mode, it is 1023 bytes
#         elif xfer_type == Transfer.CONTROL:
#             size_limit = 64
#         else:
#             size_limit = 512

#         if not isinstance(max_size, int) or not max_size in range(0, size_limit+1):
#             raise TypeError("Maximum packet size must be an integer in [0..{}], not '{!r}'"
#                             .format(size_limit, max_size))

#         if xfer_type == Transfer.CONTROL:
#             port = stream.Endpoint([("empty", 1), ("data", 8)])
#         else:
#             port = stream.Endpoint([("data", 8)])
#         self._input_map[ep_addr] = port, max_size, xfer_type
#         return port

#     def output_port(self, ep_addr, max_size, xfer_type):
#         if not isinstance(ep_addr, int) or not ep_addr in range(0, 16):
#             raise TypeError("Endpoint address must be an integer in [0..16), not '{!r}'"
#                             .format(ep_addr))
#         if ep_addr in self._output_map:
#             raise ValueError("An output port for endpoint {} has already been requested"
#                              .format(ep_addr))
#         if not isinstance(xfer_type, Transfer):
#             raise TypeError("Transfer type must be a member of the Transfer enum, not '{!r}'"
#                             .format(xfer_type))

#         if xfer_type == Transfer.ISOCHRONOUS:
#             size_limit = 1024 # FIXME in FS mode, it is 1023 bytes
#         elif xfer_type == Transfer.CONTROL:
#             size_limit = 64
#         else:
#             size_limit = 512

#         if not isinstance(max_size, int) or not max_size in range(0, size_limit+1):
#             raise TypeError("Maximum packet size must be an integer in [0..{}], not '{!r}'"
#                             .format(size_limit, max_size))

#         if xfer_type == Transfer.CONTROL:
#             port = stream.Endpoint([("setup", 1), ("data", 8)])
#         else:
#             port = stream.Endpoint([("data", 8)])
#         self._output_map[ep_addr] = port, max_size, xfer_type
#         return port

    def elaborate(self, platform):
        m = Module()

        controller = m.submodules.controller = USBController(self.phy)
        # i_arbiter  = m.submodules.i_arbiter  = USBInputArbiter(self._input_map)
        # i_buffer   = m.submodules.i_buffer   = USBInputBuffer(self._input_map)
        # o_arbiter  = m.submodules.o_arbiter  = USBOutputArbiter(self._output_map)
        # o_buffer   = m.submodules.o_buffer   = USBOutputBuffer(self._output_map)
        i_mux = m.submodules.i_mux = self._input_mux
        o_mux = m.submodules.o_mux = self._output_mux

        m.d.comb += [
            o_mux.w_ep.eq(controller.source_write.ep),
            o_mux.w_stb.eq(controller.source_write.valid),
            controller.source_write.ready.eq(o_mux.w_rdy),
            controller.source_data.connect(o_mux.sink),
            controller.write_xfer.eq(o_mux.write_xfer), # FIXME rm

            i_mux.r_ep.eq(controller.sink_read.ep),
            i_mux.r_stb.eq(controller.sink_read.valid),
            controller.sink_read.ready.eq(i_mux.r_rdy),
            i_mux.source.connect(controller.sink_data),
            controller.read_xfer.eq(i_mux.read_xfer), # FIXME rm
            # TODO i_mux.recv_ack.eq(controller.host_ack),

            # # phy -> controller -> o_buffer
            # controller.source_write.connect(o_buffer.sink_write),
            # controller.source_data.connect(o_buffer.sink_data),
            # controller.write_xfer.eq(o_buffer.write_xfer),

            # # o_buffer -> o_arbiter -> endpoints
            # o_buffer.recv_zlp.eq(controller.host_zlp),
            # o_arbiter.sink_read.connect(o_buffer.source_read),
            # o_buffer.source_data.connect(o_arbiter.sink_data),

            # # endpoints -> i_arbiter -> i_buffer
            # i_arbiter.source_write.connect(i_buffer.sink_write),
            # i_arbiter.source_data.connect(i_buffer.sink_data),
            # controller.sink_read.connect(i_buffer.source_read),

            # # i_buffer -> controller -> phy
            # i_buffer.source_data.connect(controller.sink_data),
            # controller.read_xfer.eq(i_buffer.read_xfer),
            # i_buffer.recv_ack.eq(controller.host_ack),

            self.sof.eq(controller.sof)
        ]

        return m
