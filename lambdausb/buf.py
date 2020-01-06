from collections import OrderedDict # FIXME

from nmigen import *
from nmigen.lib.fifo import *
from nmigen.utils import bits_for, log2_int

from .protocol import Transfer # FIXME


__all__ = ["DoubleBuffer", "InputMultiplexer", "OutputMultiplexer"]


# TODO move
class _USBEndpoint:
    def __init__(self, addr, xfer_type, max_size, buffered=True):
        if not isinstance(addr, int) or addr not in range(0, 16):
            raise ValueError("Endpoint address must be an integer in [0..15], not '{!r}'"
                             .format(addr))
        if not isinstance(xfer_type, Transfer):
            raise TypeError("Invalid transfer type; must be a member of the Transfer enum, "
                            "not '{!r}'".format(xfer_type))

        if xfer_type == Transfer.ISOCHRONOUS:
            size_limit = 1024 # FIXME: in FS mode, it is 1023 bytes.
        elif xfer_type == Transfer.CONTROL:
            size_limit = 64
        else:
            size_limit = 512

        if not isinstance(max_size, int) or max_size not in range(0, size_limit+1):
            raise TypeError("Maximum packet size must be an integer in [0..{}], not '{!r}'"
                            .format(size_limit, max_size))

        self.addr      = addr
        self.xfer_type = xfer_type
        self.max_size  = max_size
        self.buffered  = buffered


class InputEndpoint(_USBEndpoint):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.w_stb  = Signal()
        self.w_lst  = Signal()
        self.w_data = Signal(8)
        self.w_zlp  = Signal()
        self.w_rdy  = Signal()
        self.w_ack  = Signal()

        self.sof    = Signal()


class OutputEndpoint(_USBEndpoint):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.r_stb   = Signal()
        self.r_lst   = Signal()
        self.r_data  = Signal(8)
        self.r_setup = Signal()
        self.r_drop  = Signal() if not self.buffered else Const(0)
        self.r_rdy   = Signal()

        self.sof     = Signal()


class DoubleBuffer(Elaboratable):
    def __init__(self, *, depth, width=8, with_ack=False):
        self.w_stb     = Signal()
        self.w_lst     = Signal()
        self.w_data    = Signal(width)
        self.w_drop    = Signal()
        self.w_rdy     = Signal()

        self.r_stb     = Signal()
        self.r_lst     = Signal()
        self.r_data    = Signal(width)
        self.r_rdy     = Signal()
        if with_ack:
            self.r_ack = Signal()

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
                        buf.w_en.eq(self.w_stb),
                        buf.w_data.eq(self.w_data),
                    ]
                    with m.If(self.w_stb):
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
                with m.If(self.w_stb & self.w_lst):
                    m.next = "WAIT"

            with m.State("WAIT"):
                with m.If(~dbuf[0].valid):
                    m.d.sync += dbuf[0].w_addr.eq(0)
                    m.next = "WRITE-0"
                with m.Elif(~dbuf[1].valid):
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
                        self.r_stb.eq(1),
                        self.r_data.eq(buf.r_data),
                        self.r_lst.eq(buf.r_addr == self.depth - 1),
                    ]
                    with m.If(self.r_rdy):
                        with m.If(self.r_lst):
                            m.d.sync += buf.r_addr.eq(0)
                            m.next = "WAIT"
                        with m.Else():
                            m.d.sync += buf.r_addr.eq(buf.r_addr + 1)

        consume = Signal()
        if self._with_ack:
            m.d.comb += consume.eq(self.r_ack)
        else:
            m.d.comb += consume.eq(self.r_rdy & self.r_stb & self.r_lst)

        with m.If(consume):
            m.d.sync += [
                dbuf[lru].valid.eq(0),
                lru.eq(~lru)
            ]

        return m


class OutputMultiplexer(Elaboratable):
    def __init__(self):
        self.ep_addr = Signal(range(16))
        self.ep_rdy  = Signal()
        self.ep_stb  = Signal()
        self.ep_xfer = Signal(2, decoder=Transfer)

        self.w_stb   = Signal()
        self.w_lst   = Signal()
        self.w_data  = Signal(8)
        self.w_setup = Signal()
        self.w_drop  = Signal()
        self.w_rdy   = Signal()

        self._endpoints = OrderedDict()

    def add_endpoint(self, endpoint):
        if not isinstance(endpoint, OutputEndpoint):
            raise ValueError("Endpoint must be an OutputEndpoint, not '{!r}'"
                             .format(endpoint))
        if endpoint.addr in self._endpoints:
            raise ValueError("Endpoint address 0x{:02x} has already been allocated"
                             .format(endpoint.addr))
        self._endpoints[endpoint.addr] = endpoint

    def elaborate(self, platform):
        m = Module()

        ports = OrderedDict({addr: Record([
            ("w_stb",   1),
            ("w_lst",   1),
            ("w_data",  8),
            ("w_setup", 1),
            ("w_drop",  1),
            ("w_rdy",   1),
        ]) for addr in self._endpoints})

        for addr, ep in self._endpoints.items():
            port = ports[addr]
            if ep.buffered:
                obuf = DoubleBuffer(depth=ep.max_size, width=len(self.w_data) + len(self.w_setup))
                m.submodules["obuf_{}".format(addr)] = obuf
                m.d.comb += [
                    obuf.w_stb .eq(port.w_stb),
                    obuf.w_lst .eq(port.w_lst),
                    obuf.w_data.eq(Cat(port.w_data, port.w_setup)),
                    obuf.w_drop.eq(port.w_drop),
                    port.w_rdy .eq(obuf.w_rdy),

                    ep.r_stb   .eq(obuf.r_stb),
                    ep.r_lst   .eq(obuf.r_lst),
                    Cat(ep.r_data, ep.r_setup).eq(obuf.r_data),
                    obuf.r_rdy .eq(ep.r_rdy),
                ]
            else:
                m.d.comb += [
                    ep.r_stb  .eq(port.w_stb),
                    ep.r_lst  .eq(port.w_lst),
                    ep.r_data .eq(port.w_data),
                    ep.r_setup.eq(port.w_setup),
                    ep.r_drop .eq(port.w_drop),
                    port.w_rdy.eq(ep.r_rdy),
                ]

        with m.Switch(self.ep_addr):
            for addr, port in ports.items():
                ep = self._endpoints[addr]
                with m.Case(addr):
                    m.d.comb += [
                        self.ep_rdy .eq(port.w_rdy),
                        self.ep_xfer.eq(ep.xfer_type),
                    ]
            with m.Case():
                m.d.comb += self.ep_rdy.eq(0)

        port_addr = Signal.like(self.ep_addr)

        with m.If(self.ep_stb & self.ep_rdy):
            m.d.sync += port_addr.eq(self.ep_addr)

        with m.Switch(port_addr):
            for addr, port in ports.items():
                with m.Case(addr):
                    m.d.comb += [
                        port.w_stb  .eq(self.w_stb),
                        port.w_lst  .eq(self.w_lst),
                        port.w_data .eq(self.w_data),
                        port.w_setup.eq(self.w_setup),
                        self.w_rdy  .eq(port.w_rdy),
                    ]

        return m


class InputMultiplexer(Elaboratable):
    def __init__(self):
        self.ep_addr = Signal(range(16))
        self.ep_rdy  = Signal()
        self.ep_stb  = Signal()
        self.ep_xfer = Signal(2, decoder=Transfer)

        self.r_stb   = Signal()
        self.r_lst   = Signal()
        self.r_data  = Signal()
        self.r_zlp   = Signal()
        self.r_rdy   = Signal()
        self.r_ack   = Signal()

        self._endpoints = OrderedDict()

    def add_endpoint(self, endpoint):
        if not isinstance(endpoint, InputEndpoint):
            raise ValueError("Endpoint must be an InputEndpoint, not '{!r}'"
                             .format(endpoint))
        if endpoint.addr in self._endpoints:
            raise ValueError("Endpoint address 0x{:02x} has already been allocated"
                             .format(endpoint.addr))
        self._endpoints[endpoint.addr] = endpoint

    def elaborate(self, platform):
        m = Module()

        ports = OrderedDict({addr: Record([
            ("r_stb",   1),
            ("r_lst",   1),
            ("r_data",  8),
            ("r_zlp",   1),
            ("r_rdy",   1),
            ("r_ack",   1),
        ]) for addr in self._endpoints})

        for addr, ep in self._endpoints.items():
            port = ports[addr]
            if ep.buffered:
                ibuf = DoubleBuffer(depth=ep.max_size, width=len(self.r_data) + len(self.r_zlp),
                                    with_ack=True)
                m.submodules["ibuf_{}".format(addr)] = ibuf
                m.d.comb += [
                    ibuf.w_stb .eq(ep.w_stb),
                    ibuf.w_lst .eq(ep.w_lst),
                    ibuf.w_data.eq(Cat(ep.w_data, ep.w_zlp)),
                    ep.w_rdy   .eq(ibuf.w_rdy),

                    port.r_stb .eq(ibuf.r_stb),
                    port.r_lst .eq(ibuf.r_lst),
                    Cat(port.r_data, port.r_zlp).eq(ibuf.r_data),
                    ibuf.r_rdy .eq(port.r_rdy),
                    ibuf.r_ack .eq(port.r_ack),
                ]
            else:
                m.d.comb += [
                    port.r_stb .eq(ep.w_stb),
                    port.r_lst .eq(ep.w_lst),
                    port.r_data.eq(ep.w_data),
                    port.r_zlp .eq(ep.w_zlp),
                    ep.w_rdy   .eq(port.r_rdy),
                    ep.w_ack   .eq(port.r_ack),
                ]

        with m.Switch(self.ep_addr):
            for addr, port in ports.items():
                ep = self._endpoints[addr]
                with m.Case(addr):
                    m.d.comb += [
                        self.ep_rdy .eq(port.r_rdy),
                        self.ep_xfer.eq(ep.xfer_type),
                    ]
            with m.Case():
                m.d.comb += self.ep_rdy.eq(0)

        port_addr = Signal.like(self.ep_addr)

        with m.If(self.ep_stb & self.ep_rdy):
            m.d.sync += port_addr.eq(self.ep_addr)

        with m.Switch(port_addr):
            for addr, port in ports.items():
                with m.Case(addr):
                    m.d.comb += [
                        self.r_stb .eq(port.r_stb),
                        self.r_lst .eq(port.r_lst),
                        self.r_data.eq(port.r_data),
                        self.r_zlp .eq(port.r_zlp),
                        port.r_rdy .eq(self.r_rdy),
                        port.r_ack .eq(self.r_ack),
                    ]

        return m
