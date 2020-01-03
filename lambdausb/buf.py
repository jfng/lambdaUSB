from collections import OrderedDict # FIXME

from nmigen import *
from nmigen.lib.fifo import *
from nmigen.utils import bits_for, log2_int

from .lib import stream
from .protocol import Direction, Transfer


__all__ = ["USBInputBuffer", "USBOutputBuffer", "USBOutputMultiplexer"]


# class USBInputBuffer(Elaboratable):
#     def __init__(self, endpoint_map):
#         self.endpoint_map = endpoint_map

#         self.sink_write   = stream.Endpoint([("ep", 4)])
#         self.sink_data    = stream.Endpoint([("empty", 1), ("data", 8)])
#         self.source_read  = stream.Endpoint([("ep", 4)])
#         self.source_data  = stream.Endpoint([("empty", 1), ("data", 8)])

#         self.read_xfer    = Signal(2)
#         self.recv_ack     = Signal()

#     def elaborate(self, platform):
#         m = Module()

#         ep_info = Array(Record([("max_size", bits_for(1024)), ("xfer_type", 2)])
#                         for _ in self.endpoint_map)
#         for i, (ep_addr, (port, max_size, xfer_type)) in enumerate(self.endpoint_map.items()):
#             m.d.comb += [
#                 ep_info[i].max_size.eq(Const(max_size)),
#                 ep_info[i].xfer_type.eq(Const(xfer_type))
#             ]

#         rd_index  = Signal.range(len(self.endpoint_map))
#         rd_bad_ep = Signal()

#         with m.Switch(self.source_read.ep):
#             for i, ep_addr in enumerate(self.endpoint_map):
#                 with m.Case(ep_addr):
#                     m.d.comb += rd_index.eq(i)
#             with m.Case():
#                 m.d.comb += rd_bad_ep.eq(1)

#         wr_index  = Signal.like(rd_index)
#         wr_bad_ep = Signal()

#         with m.Switch(self.sink_write.ep):
#             for i, ep_addr in enumerate(self.endpoint_map):
#                 with m.Case(ep_addr):
#                     m.d.comb += wr_index.eq(i)
#             with m.Case():
#                 m.d.comb += wr_bad_ep.eq(1)

#         m.d.comb += self.read_xfer.eq(ep_info[rd_index].xfer_type)

#         # state memory

#         buf_fields = [("valid", 1), ("level", bits_for(1024))]

#         state_rp1_data = Record([("lru", 1), ("buf1", buf_fields), ("buf2", buf_fields)])
#         state_rp2_data = Record.like(state_rp1_data)
#         state_wp_data  = Record.like(state_rp1_data)

#         state_mem = Memory(width=len(state_rp1_data), depth=len(self.endpoint_map))
#         state_rp1 = m.submodules.state_rp1 = state_mem.read_port()
#         state_rp2 = m.submodules.state_rp2 = state_mem.read_port()
#         state_wp  = m.submodules.state_wp  = state_mem.write_port()

#         m.d.comb += [
#             state_rp1_data.eq(state_rp1.data),
#             state_rp2_data.eq(state_rp2.data),
#             state_wp.data.eq(state_wp_data)
#         ]

#         # data memory

#         data_rp_addr = Record([("index", rd_index.width), ("buf_sel", 1), ("offset", log2_int(1024))])
#         data_wp_addr = Record.like(data_rp_addr)

#         data_mem = Memory(width=8, depth=2**len(data_rp_addr))
#         data_rp  = m.submodules.data_rp = data_mem.read_port(transparent=False)
#         data_wp  = m.submodules.data_wp = data_mem.write_port()

#         data_rp.en.reset = 0

#         m.d.comb += [
#             data_rp.addr.eq(data_rp_addr),
#             data_wp.addr.eq(data_wp_addr)
#         ]

#         # control FSMs

#         is_empty = Array(Signal(len(self.endpoint_map), reset=2**len(self.endpoint_map)-1, name="is_empty"))
#         is_full  = Array(Signal(len(self.endpoint_map), name="is_full"))

#         rd_buf_sel = Signal.like(data_rp_addr.buf_sel)
#         rd_offset  = Signal.range(1026)
#         rd_buf     = Record(buf_fields)
#         rd_done    = Signal()

#         m.d.comb += [
#             self.source_read.ready.eq(~rd_bad_ep & ~is_empty[rd_index]),
#             self.sink_write.ready.eq(~wr_bad_ep & ~is_full[wr_index])
#         ]

#         with m.If(self.source_read.ready & self.source_read.valid):
#             m.d.comb += state_rp1.addr.eq(rd_index)
#         with m.Else():
#             m.d.comb += state_rp1.addr.eq(data_rp_addr.index)

#         with m.If(self.sink_write.ready & self.sink_write.valid):
#             m.d.comb += state_rp2.addr.eq(wr_index)
#         with m.Else():
#             m.d.comb += state_rp2.addr.eq(data_wp_addr.index)

#         with m.FSM(name="read_fsm") as read_fsm:
#             with m.State("IDLE"):
#                 # m.d.comb += self.source_read.ready.eq(~rd_bad_ep & ~is_empty[rd_index])
#                 with m.If(self.source_read.ready & self.source_read.valid):
#                     m.d.sync += data_rp_addr.index.eq(rd_index)
#                     m.next = "READ-0"

#             with m.State("READ-0"):
#                 with m.If(state_rp1_data.buf1.valid & state_rp1_data.buf2.valid):
#                     m.d.comb += data_rp_addr.buf_sel.eq(state_rp1_data.lru)
#                 with m.Else():
#                     m.d.comb += data_rp_addr.buf_sel.eq(state_rp1_data.buf2.valid)
#                 m.d.sync += [
#                     rd_buf_sel.eq(data_rp_addr.buf_sel),
#                     rd_offset.eq(1),
#                     rd_buf.eq(Mux(data_rp_addr.buf_sel, state_rp1_data.buf2, state_rp1_data.buf1))
#                 ]
#                 m.d.comb += [
#                     data_rp_addr.offset.eq(0),
#                     data_rp.en.eq(1)
#                 ]
#                 m.next = "READ-1"

#             with m.State("READ-1"):
#                 m.d.comb += [
#                     self.source_data.valid.eq(1),
#                     self.source_data.empty.eq(rd_buf.level == 0),
#                     self.source_data.data.eq(Mux(rd_buf.level.bool(), data_rp.data, 0x00)),
#                     self.source_data.last.eq((rd_buf.level == 0) | (rd_buf.level == rd_offset))
#                 ]
#                 with m.If(self.source_data.ready):
#                     with m.If(self.source_data.last):
#                         m.next = "IDLE"
#                     with m.Else():
#                         m.d.sync += rd_offset.eq(rd_offset + 1)
#                         m.d.comb += [
#                             data_rp_addr.buf_sel.eq(rd_buf_sel),
#                             data_rp_addr.offset.eq(rd_offset),
#                             data_rp.en.eq(1)
#                         ]

#         with m.FSM(name="write_fsm") as write_fsm:
#             with m.State("IDLE"):
#                 with m.If(self.sink_write.ready & self.sink_write.valid):
#                     m.d.sync += data_wp_addr.index.eq(wr_index)
#                     m.next = "WRITE-0"

#             with m.State("WRITE-0"):
#                 m.d.sync += data_wp_addr.buf_sel.eq(state_rp2_data.buf1.valid)
#                 with m.If(state_rp2_data.buf1.valid):
#                     m.d.sync += data_wp_addr.offset.eq(state_rp2_data.buf2.level)
#                 with m.Else():
#                     m.d.sync += data_wp_addr.offset.eq(state_rp2_data.buf1.level)
#                 m.next = "WRITE-1"

#             with m.State("WRITE-1"):
#                 with m.If(rd_done): # Wait because state_wp is being driven.
#                     m.d.comb += self.sink_data.ready.eq(0)
#                 with m.Else():
#                     m.d.comb += self.sink_data.ready.eq(~wr_bad_ep & (wr_index == data_wp_addr.index))

#                 with m.If(~self.sink_write.valid | wr_bad_ep | (wr_index != data_wp_addr.index)):
#                     m.next = "IDLE"
#                 with m.Elif(self.sink_data.ready & self.sink_data.valid):
#                     with m.If(self.sink_data.last | (data_wp_addr.offset + 1 == ep_info[wr_index].max_size)): # TODO handle overflows
#                         m.next = "IDLE"
#                     with m.Else():
#                         m.d.sync += data_wp_addr.offset.eq(data_wp_addr.offset + 1)
#                     m.d.comb += [
#                         data_wp.data.eq(self.sink_data.data),
#                         data_wp.en.eq(1)
#                     ]

#         # state update

#         with m.If(ep_info[data_rp_addr.index].xfer_type == Transfer.ISOCHRONOUS):
#             m.d.comb += rd_done.eq(self.source_data.valid & self.source_data.last & self.source_data.ready)
#         with m.Else():
#             m.d.comb += rd_done.eq(self.recv_ack)

#         with m.If(rd_done):
#             m.d.sync += is_full[data_rp_addr.index].eq(0)
#             with m.If(rd_buf_sel):
#                 m.d.sync += is_empty[data_rp_addr.index].eq(~state_rp1_data.buf1.valid)
#             with m.Else():
#                 m.d.sync += is_empty[data_rp_addr.index].eq(~state_rp1_data.buf2.valid)

#             m.d.comb += [
#                 state_wp.addr.eq(data_rp_addr.index),
#                 state_wp.en.eq(1),
#                 state_wp_data.lru.eq(state_rp1_data.lru),
#                 state_wp_data.buf1.eq(Mux(rd_buf_sel, state_rp1_data.buf1, 0)),
#                 state_wp_data.buf2.eq(Mux(rd_buf_sel, 0, state_rp1_data.buf2))
#             ]
#         with m.Elif(self.sink_data.valid & self.sink_data.ready):
#             with m.If(self.sink_data.last | (data_wp_addr.offset + 1 == ep_info[wr_index].max_size)): # FIXME factor
#                 m.d.sync += is_empty[wr_index].eq(0)
#                 with m.If(data_wp_addr.buf_sel):
#                     m.d.sync += is_full[wr_index].eq(state_rp2_data.buf1.valid)
#                 with m.Else():
#                     m.d.sync += is_full[wr_index].eq(state_rp2_data.buf2.valid)

#             m.d.comb += [
#                 state_wp.addr.eq(wr_index),
#                 state_wp.en.eq(1)
#             ]

#             with m.If(self.sink_data.last | (data_wp_addr.offset + 1 == ep_info[wr_index].max_size)): # idem
#                 m.d.comb += state_wp_data.lru.eq(~data_wp_addr.buf_sel)
#             with m.Else():
#                 m.d.comb += state_wp_data.lru.eq(state_rp2_data.lru)

#             with m.If(data_wp_addr.buf_sel):
#                 m.d.comb += state_wp_data.buf1.eq(state_rp2_data.buf1)
#                 m.d.comb += [
#                     state_wp_data.buf2.valid.eq(self.sink_data.last | (data_wp_addr.offset + 1 == ep_info[wr_index].max_size)), # idem
#                     state_wp_data.buf2.level.eq(Mux(self.sink_data.empty, 0, data_wp_addr.offset + 1))
#                 ]
#             with m.Else():
#                 m.d.comb += state_wp_data.buf2.eq(state_rp2_data.buf2)
#                 m.d.comb += [
#                     state_wp_data.buf1.valid.eq(self.sink_data.last | (data_wp_addr.offset + 1 == ep_info[wr_index].max_size)), # idem
#                     state_wp_data.buf1.level.eq(Mux(self.sink_data.empty, 0, data_wp_addr.offset + 1))
#                 ]

#         return m


# class USBOutputBuffer(Elaboratable):
#     def __init__(self, endpoint_map):
#         self.endpoint_map = endpoint_map

#         self.sink_write   = stream.Endpoint([("ep", 4)])
#         self.sink_data    = stream.Endpoint([("setup", 1), ("data", 8), ("crc_ok", 1)])
#         self.source_read  = stream.Endpoint([("ep", 4)])
#         self.source_data  = stream.Endpoint([("setup", 1), ("data", 8)])

#         self.write_xfer   = Signal(2)
#         self.recv_zlp     = Signal()

#     def elaborate(self, platform):
#         m = Module()

#         ep_info = Array(Record([("max_size", bits_for(1024)), ("xfer_type", 2)])
#                         for _ in self.endpoint_map)
#         for i, (ep_addr, (port, max_size, xfer_type)) in enumerate(self.endpoint_map.items()):
#             m.d.comb += [
#                 ep_info[i].max_size.eq(Const(max_size)),
#                 ep_info[i].xfer_type.eq(Const(xfer_type))
#             ]

#         rd_index  = Signal.range(len(self.endpoint_map))
#         rd_bad_ep = Signal()

#         with m.Switch(self.source_read.ep):
#             for i, ep_addr in enumerate(self.endpoint_map):
#                 with m.Case(ep_addr):
#                     m.d.comb += rd_index.eq(i)
#             with m.Case():
#                 m.d.comb += rd_bad_ep.eq(1)

#         wr_index  = Signal.like(rd_index)
#         wr_bad_ep = Signal()

#         with m.Switch(self.sink_write.ep):
#             for i, ep_addr in enumerate(self.endpoint_map):
#                 with m.Case(ep_addr):
#                     m.d.comb += wr_index.eq(i)
#             with m.Case():
#                 m.d.comb += wr_bad_ep.eq(1)

#         m.d.comb += self.write_xfer.eq(ep_info[wr_index].xfer_type)

#         # state memory

#         buf_fields = [("valid", 1), ("setup", 1), ("level", bits_for(1024))]

#         state_rp1_data = Record([("lru", 1), ("buf1", buf_fields), ("buf2", buf_fields)])
#         state_rp2_data = Record.like(state_rp1_data)
#         state_wp_data  = Record.like(state_rp1_data)

#         state_mem = Memory(width=len(state_rp1_data), depth=len(self.endpoint_map))
#         state_rp1 = m.submodules.state_rp1 = state_mem.read_port()
#         state_rp2 = m.submodules.state_rp2 = state_mem.read_port()
#         state_wp  = m.submodules.state_wp  = state_mem.write_port()

#         m.d.comb += [
#             state_rp1_data.eq(state_rp1.data),
#             state_rp2_data.eq(state_rp2.data),
#             state_wp.data.eq(state_wp_data)
#         ]

#         # data memory

#         data_rp_addr = Record([("index", rd_index.width), ("buf_sel", 1), ("offset", log2_int(1024))])
#         data_wp_addr = Record.like(data_rp_addr)

#         data_mem = Memory(width=8, depth=2**len(data_rp_addr))
#         data_rp  = m.submodules.data_rp = data_mem.read_port(transparent=False)
#         data_wp  = m.submodules.data_wp = data_mem.write_port()

#         data_rp.en.reset = 0

#         m.d.comb += [
#             data_rp.addr.eq(data_rp_addr),
#             data_wp.addr.eq(data_wp_addr)
#         ]

#         # control FSMs

#         is_empty = Array(Signal(len(self.endpoint_map), reset=2**len(self.endpoint_map)-1, name="is_empty"))
#         is_full  = Array(Signal(len(self.endpoint_map), name="is_full"))
#         is_last  = Array(Signal(2, name=f"ep{addr}_last") for addr in self.endpoint_map)

#         rd_buf_sel = Signal.like(data_rp_addr.buf_sel)
#         rd_offset  = Signal.range(1026)
#         rd_buf     = Record(buf_fields)
#         rd_done    = Signal()

#         m.d.comb += [
#             self.source_read.ready.eq(~rd_bad_ep & ~is_empty[rd_index]),
#             self.sink_write.ready.eq(~wr_bad_ep & ~is_full[wr_index])
#         ]

#         with m.If(self.source_read.ready & self.source_read.valid):
#             m.d.comb += state_rp1.addr.eq(rd_index)
#         with m.Else():
#             m.d.comb += state_rp1.addr.eq(data_rp_addr.index)

#         with m.If(self.sink_write.ready & self.sink_write.valid):
#             m.d.comb += state_rp2.addr.eq(wr_index)
#         with m.Else():
#             m.d.comb += state_rp2.addr.eq(data_wp_addr.index)

#         with m.FSM(name="read_fsm") as read_fsm:
#             with m.State("IDLE"):
#                 with m.If(self.source_read.ready & self.source_read.valid):
#                     m.d.sync += data_rp_addr.index.eq(rd_index)
#                     m.next = "READ-0"

#             with m.State("READ-0"):
#                 with m.If(state_rp1_data.buf1.valid & state_rp1_data.buf2.valid):
#                     m.d.comb += data_rp_addr.buf_sel.eq(state_rp1_data.lru)
#                 with m.Else():
#                     m.d.comb += data_rp_addr.buf_sel.eq(state_rp1_data.buf2.valid)
#                 m.d.sync += [
#                     rd_buf_sel.eq(data_rp_addr.buf_sel),
#                     rd_offset.eq(1),
#                     rd_buf.eq(Mux(data_rp_addr.buf_sel, state_rp1_data.buf2, state_rp1_data.buf1))
#                 ]
#                 m.d.comb += [
#                     data_rp_addr.offset.eq(0),
#                     data_rp.en.eq(1)
#                 ]
#                 m.next = "READ-1"

#             with m.State("READ-1"):
#                 rd_last = Signal()
#                 m.d.comb += [
#                     rd_last.eq(is_last[data_rp_addr.index].bit_select(rd_buf_sel, 1)),
#                     self.source_data.valid.eq(1),
#                     self.source_data.setup.eq(rd_buf.setup),
#                     self.source_data.data.eq(data_rp.data),
#                     self.source_data.last.eq(rd_last & (rd_offset == rd_buf.level))
#                 ]
#                 with m.If(self.source_data.ready):
#                     with m.If(rd_offset == rd_buf.level):
#                         m.d.comb += rd_done.eq(1)
#                         m.next = "IDLE"
#                     with m.Else():
#                         m.d.sync += rd_offset.eq(rd_offset + 1)
#                         m.d.comb += [
#                             data_rp_addr.buf_sel.eq(rd_buf_sel),
#                             data_rp_addr.offset.eq(rd_offset),
#                             data_rp.en.eq(1)
#                         ]

#         with m.FSM(name="write_fsm") as write_fsm:
#             with m.State("IDLE"):
#                 with m.If(self.sink_write.ready & self.sink_write.valid):
#                     m.d.sync += data_wp_addr.index.eq(wr_index)
#                     m.next = "WRITE-0"

#             with m.State("WRITE-0"):
#                 m.d.sync += [
#                     data_wp_addr.buf_sel.eq(state_rp2_data.buf1.valid),
#                     data_wp_addr.offset.eq(0)
#                 ]
#                 m.next = "WRITE-1"

#             with m.State("WRITE-1"):
#                 with m.If(rd_done): # Wait because state_wp is being driven.
#                     m.d.comb += self.sink_data.ready.eq(~self.sink_data.last)
#                 with m.Else():
#                     m.d.comb += self.sink_data.ready.eq(1)

#                 with m.If(self.recv_zlp):
#                     # The host sent a zero-length packet. These are used to mark the previous
#                     # packet (sent to this endpoint) as the last of an OUT transfer.
#                     m.d.sync += is_last[data_wp_addr.index].eq(1 << ~data_wp_addr.buf_sel)
#                     m.next = "IDLE"
#                 with m.Elif(self.sink_data.ready & self.sink_data.valid):
#                     with m.If(self.sink_data.last): # TODO drop packet if overflow
#                         m.next = "IDLE"
#                     with m.Else():
#                         m.d.sync += data_wp_addr.offset.eq(data_wp_addr.offset + 1)
#                     m.d.comb += [
#                         data_wp.data.eq(self.sink_data.data),
#                         data_wp.en.eq(1)
#                     ]

#         # state update

#         with m.If(rd_done):
#             m.d.sync += is_full[data_rp_addr.index].eq(0)
#             with m.If(rd_buf_sel):
#                 m.d.sync += is_empty[data_rp_addr.index].eq(~state_rp1_data.buf1.valid)
#             with m.Else():
#                 m.d.sync += is_empty[data_rp_addr.index].eq(~state_rp1_data.buf2.valid)

#             m.d.comb += [
#                 state_wp.addr.eq(data_rp_addr.index),
#                 state_wp.en.eq(1),
#                 state_wp_data.lru.eq(state_rp1_data.lru),
#                 state_wp_data.buf1.eq(Mux(rd_buf_sel, state_rp1_data.buf1, 0)),
#                 state_wp_data.buf2.eq(Mux(rd_buf_sel, 0, state_rp1_data.buf2))
#             ]
#         with m.Elif(self.sink_data.valid & self.sink_data.last & self.sink_data.crc_ok & self.sink_data.ready):
#             m.d.sync += is_empty[data_wp_addr.index].eq(0)
#             with m.If(data_wp_addr.buf_sel):
#                 m.d.sync += [
#                     is_full[data_wp_addr.index].eq(state_rp2_data.buf1.valid),
#                     is_last[data_wp_addr.index][1].eq(data_wp_addr.offset + 1 != ep_info[data_wp_addr.index].max_size)
#                 ]
#             with m.Else():
#                 m.d.sync += [
#                     is_full[data_wp_addr.index].eq(state_rp2_data.buf2.valid),
#                     is_last[data_wp_addr.index][0].eq(data_wp_addr.offset + 1 != ep_info[data_wp_addr.index].max_size)
#                 ]

#             m.d.comb += [
#                 state_wp.addr.eq(data_wp_addr.index),
#                 state_wp.en.eq(1),
#                 state_wp_data.lru.eq(~data_wp_addr.buf_sel)
#             ]

#             with m.If(data_wp_addr.buf_sel):
#                 m.d.comb += state_wp_data.buf1.eq(state_rp2_data.buf1)
#                 m.d.comb += [
#                     state_wp_data.buf2.valid.eq(1),
#                     state_wp_data.buf2.setup.eq(self.sink_data.setup),
#                     state_wp_data.buf2.level.eq(data_wp_addr.offset + 1)
#                 ]
#             with m.Else():
#                 m.d.comb += state_wp_data.buf2.eq(state_rp2_data.buf2)
#                 m.d.comb += [
#                     state_wp_data.buf1.valid.eq(1),
#                     state_wp_data.buf1.setup.eq(self.sink_data.setup),
#                     state_wp_data.buf1.level.eq(data_wp_addr.offset + 1)
#                 ]

#         return m


class DoubleBuffer(Elaboratable):
    def __init__(self, *, depth, width=8, with_ack=False):
        self.r_rdy     = Signal()
        self.r_en      = Signal()
        self.r_data    = Signal(width)
        self.r_lst     = Signal()
        if with_ack:
            self.r_ack = Signal()

        self.w_rdy     = Signal()
        self.w_en      = Signal()
        self.w_data    = Signal(width)
        self.w_lst     = Signal()
        self.w_drop    = Signal()

        self.depth     = depth
        self.width     = width
        self._with_ack = with_ack

    def elaborate(self, platform):
        m = Module()

        dbuf = [Record([("w_addr", range(self.depth)), ("w_data", self.width), ("w_en", 1),
                        ("r_addr", range(self.depth)), ("r_data", self.width),
                        ("valid",  1)])
                 for _ in range(2)]

        for i, port in dbuf:
            mem = Memory(depth=self.depth, width=self.width)
            m.submodules[f"buf{i}_wp"] = wp = mem.write_port()
            m.submodules[f"buf{i}_rp"] = rp = mem.read_port()
            m.d.comb += [
                wp.addr.eq(port.w_addr),
                wp.data.eq(port.w_data),
                wp.en  .eq(port.w_en),
                rp.addr.eq(port.r_addr),
                port.r_data.eq(rp.data),
            ]

        lru = Signal()

        with m.FSM() as write_fsm:
            for i, buf in enumerate(dbuf):
                with m.State(f"WRITE-{i}"):
                    m.d.comb += [
                        self.w_rdy.eq(1),
                        buf.w_en.eq(self.w_en),
                        buf.w_data.eq(self.w_data),
                    ]
                    with m.If(self.w_en):
                        m.d.sync += buf.w_addr.eq(buf.w_addr + 1)
                        with m.If(buf.w_addr == self.depth - 1):
                            # Overflow. Flush remaining bytes.
                            m.next = "FLUSH"
                        with m.Elif(self.w_lst):
                            with m.If(~self.w_drop):
                                m.d.sync += [
                                    buf.valid.eq(1),
                                    lru.eq(i),
                                ]
                            m.next = "WAIT"

            with m.State("FLUSH"):
                m.d.comb += self.w_rdy.eq(1)
                with m.If(self.w_en & self.w_lst):
                    m.next = "WAIT"

            with m.State("WAIT"):
                with m.If(~dbuf[0].r_rdy):
                    m.d.sync += dbuf[0].w_addr.eq(0)
                    m.next = "WRITE-0"
                with m.Elif(~dbuf[1].r_rdy):
                    m.d.sync += dbuf[1].w_addr.eq(0)
                    m.next = "WRITE-1"

        with m.FSM() as read_fsm:
            with m.State("WAIT"):
                with m.If(dbuf[0].valid & ((lru == 0) | ~dbuf[1].valid)):
                    m.next = "READ-0"
                with m.Elif(dbuf[1].valid):
                    m.next = "READ-1"

            for i, buf in enumerate(dbuf):
                with m.State(f"READ-{i}"):
                    m.d.comb += [
                        self.r_rdy.eq(1),
                        self.r_data.eq(buf.r_data),
                        self.r_lst.eq(buf.r_addr == self.depth - 1),
                    ]
                    with m.If(self.r_en):
                        with m.If(self.r_lst):
                            m.d.sync += buf.r_addr.eq(0)
                            m.next = "WAIT"
                        with m.Else():
                            m.d.sync += buf.r_addr.eq(buf.r_addr + 1)

        with m.If(self.r_ack if self._with_ack else self.r_rdy & self.r_en & self.r_lst):
            m.d.sync += [
                dbuf[lru].valid.eq(0),
                lru.eq(~lru)
            ]

        return m


class USBEndpoint:
    def __init__(self, addr, dir, xfer_type, max_size, buffered=True):
        if not isinstance(addr, int) or addr not in range(0, 16):
            raise ValueError("Endpoint address must be an integer in [0..15], not '{!r}'"
                             .format(addr))
        if not isinstance(dir, Direction):
            raise ValueError("Endpoint direction must be a member of the Direction enum, "
                             "not '{!r}'".format(dir))
        if not isinstance(xfer_type, Transfer):
            raise TypeError("Endpoint transfer type must be a member of the Transfer enum, "
                            "not '{!r}'".format(xfer_type))

        if xfer_type == Transfer.ISOCHRONOUS:
            size_limit = 1024 # FIXME in FS mode, it is 1023 bytes
        elif xfer_type == Transfer.CONTROL:
            size_limit = 64
        else:
            size_limit = 512

        if not isinstance(max_size, int) or max_size not in range(0, size_limit+1):
            raise TypeError("Maximum packet size must be an integer in [0..{}], not '{!r}'"
                            .format(size_limit, max_size))

        self.addr      = addr
        self.dir       = dir
        self.xfer_type = xfer_type
        self.max_size  = max_size
        self.buffered  = buffered

        # if xfer_type == Transfer.CONTROL: TODO
        #     self.sink = stream.Endpoint([("data", 8), ("setup", 1)])
        # else:
        #     self.sink = stream.Endpoint([("data", 8)])

        self.sink = stream.Endpoint([("data", 8), ("setup", 1)])


class USBOutputMultiplexer(Elaboratable):
    def __init__(self):
        self.w_ep  = Signal(range(16))
        self.w_rdy = Signal()
        self.w_stb = Signal()
        self.sink  = stream.Endpoint([("data", 8), ("setup", 1), ("crc_ok", 1)])

        self.write_xfer = Signal(2) # FIXME remove

        self._endpoints = OrderedDict()

    def add_endpoint(self, endpoint):
        if not isinstance(endpoint, USBEndpoint):
            raise ValueError("Endpoint must be an USBEndpoint, not '{!r}'"
                             .format(endpoint))
        if endpoint.dir == Direction.INPUT:
            # TODO isinstance(OutputEndpoint)
            raise ValueError("Endpoint 0x{:02x} must be an output, not an input"
                             .format(endpoint.addr))
        if endpoint.addr in self._endpoints:
            raise ValueError("Endpoint 0x{:02x} has already be allocated"
                             .format(endpoint.addr))

        self._endpoints[endpoint.addr] = endpoint

    def elaborate(self, platform):
        m = Module()

        ports = OrderedDict()
        for addr, ep in self._endpoints.items():
            port = stream.Endpoint.like(self.sink)
            if ep.buffered:
                obuf = DoubleBuffer(depth=ep.max_size, width=len(self.sink.data) + len(self.sink.setup))
                m.submodules["obuf_{}".format(addr)] = obuf
                m.d.comb += [
                    obuf.w_en.eq(port.valid),
                    obuf.w_lst.eq(port.last),
                    obuf.w_data.eq(Cat(port.payload.data, port.payload.setup)),
                    obuf.w_drop.eq(~port.payload.crc_ok),
                    port.ready.eq(obuf.w_rdy),

                    ep.sink.valid.eq(obuf.r_rdy),
                    ep.sink.last.eq(obuf.r_lst),
                    Cat(ep.sink.data, ep.sink.setup).eq(obuf.r_data),
                    obuf.r_en.eq(ep.sink.ready),
                ]
            else:
                # m.d.comb += port.connect(ep.sink) FIXME
                m.d.comb += [
                    ep.sink.valid.eq(port.valid),
                    ep.sink.last.eq(port.last),
                    ep.sink.data.eq(port.payload.data),
                    ep.sink.setup.eq(port.payload.setup),
                    ep.sink.crc_ok.eq(port.payload.crc_ok),
                    port.ready.eq(ep.sink.ready),
                ]
            ports[addr] = port

        with m.Switch(self.w_ep):
            for addr, port in ports.items():
                with m.Case(addr):
                    m.d.comb += self.w_rdy.eq(port.ready)
                    m.d.comb += self.write_xfer.eq(Const(self._endpoints[addr].xfer_type)) # FIXME
            with m.Case():
                m.d.comb += self.w_rdy.eq(0)

        port_ep = Signal.like(self.w_ep)

        with m.If(self.w_stb & self.w_rdy):
            m.d.sync += port_ep.eq(self.w_ep)

        with m.Switch(port_ep):
            for addr, port in ports.items():
                with m.Case(addr):
                    m.d.comb += self.sink.connect(port)

        return m


class USBInputMultiplexer(Elaboratable):
    def __init__(self):
        self.r_ep   = Signal(range(16))
        self.r_rdy  = Signal()
        self.r_stb  = Signal()
        self.r_ack  = Signal()
        self.source = stream.Endpoint([("data", 8), ("empty", 1)])

        self.read_xfer = Signal(2) # FIXME remove

        self._endpoints = OrderedDict()

    def add_endpoint(self, endpoint):
        if not isinstance(endpoint, USBEndpoint):
            raise ValueError("Endpoint must be an USBEndpoint, not '{!r}'"
                             .format(endpoint))
        if endpoint.dir == Direction.OUTPUT:
            # TODO isinstance(OutputEndpoint)
            raise ValueError("Endpoint 0x{:02x} must be an input, not an output"
                             .format(endpoint.addr))
        if endpoint.addr in self._endpoints:
            raise ValueError("Endpoint 0x{:02x} has already be allocated"
                             .format(endpoint.addr))

        self._endpoints[endpoint.addr] = endpoint

    def elaborate(self, platform):
        m = Module()

        ports = OrderedDict()
        for addr, ep in self._endpoints.items():
            port = stream.Endpoint.like(self.source)
            if ep.buffered:
                ibuf = DoubleBuffer(depth=ep.max_size, width=len(self.source.payload), with_ack=True)
                m.submodules["ibuf_{}".format(addr)] = ibuf
                m.d.comb += [
                    ibuf.w_stb.eq(ep.source.valid),
                    ibuf.w_lst.eq(ep.source.last),
                    ibuf.w_data.eq(Cat(ep.source.data, ep.source.empty)),
                    ep.source.ready.eq(ibuf.w_rdy),

                    self.source.valid.eq(ibuf.r_stb), # FIXME ??
                    Cat(self.source.data, self.source.empty).eq(ibuf.r_data),
                    ibuf.r_rdy.eq(self.source.ready),
                    ibuf.r_ack.eq((self.r_ep == ep) & self.r_ack),
                    # TODO r_ack
                ]
            else:
                # m.d.comb += port.connect(self.source) FIXME
                m.d.comb += [
                    self.source.valid.eq(port.valid),
                    self.source.last.eq(port.last),
                    self.source.data.eq(port.data),
                    self.source.empty.eq(port.empty),
                    port.ready.eq(self.source.ready),
                ]
            ports[addr] = port

        with m.Switch(self.r_ep):
            for addr, port in ports.items():
                with m.Case(addr):
                    m.d.comb += self.r_rdy.eq(port.valid)
                    m.d.comb += self.read_xfer.eq(Const(self._endpoints[addr].xfer_type)) # FIXME
            with m.Case():
                m.d.comb += self.r_rdy.eq(0)

        port_ep = Signal.like(self.r_ep)

        with m.If(self.r_stb & self.r_rdy):
            m.d.sync += port_ep.eq(self.r_ep)

        with m.Switch(port_ep):
            for addr, port in ports.items():
                with m.Case(addr):
                    m.d.comb += port.connect(self.source)

        return m
