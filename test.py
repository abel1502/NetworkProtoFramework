import unittest
import logging
import transport
import socket
import packet


def transportPair(*args, **kwargs):
    s1, s2 = socket.socketpair()
    return transport.Transport(s1, *args, **kwargs), transport.Transport(s2, *args, **kwargs)


class TransportTestCase(unittest.TestCase):
    def setUp(self):
        defaultTO = 0.5  # Shorter than usual to speed up tests.
        # Since both ends are on local machine, it shouldn't break anything
        self.t1, self.t2 = transportPair(defaultTimeout=defaultTO)

    def tearDown(self):
        self.t1.close()
        self.t2.close()

    def test_meta(self):
        self.assertTrue(hasattr(self, "t1"))
        self.assertTrue(hasattr(self, "t2"))
        self.assertIsInstance(self.t1, transport.Transport)
        self.assertIsInstance(self.t2, transport.Transport)

    def test_normalExchange(self):
        data = b"Random test data"
        self.t1.write(data)
        result = self.t2.read(len(data))
        self.assertEqual(data, result)

    def test_insufficientData(self):
        data = b'1234567'
        self.t1.write(data)
        self.assertRaises(transport.Timeout, self.t2.read, len(data) + 1)

    def test_multipart(self):
        data = (b'1234', b'5678')
        self.t1.write(data[0])
        self.t1.write(data[1])
        result = self.t2.read(8)
        self.assertEqual(b''.join(data), result)

    def test_readyCheck(self):
        data = b'test'
        self.assertFalse(self.t2.hasData())
        self.t1.write(data)
        self.assertTrue(self.t2.hasData())
        self.t2.read(len(data) - 1)
        self.assertTrue(self.t2.hasData())
        self.t2.read(1)
        self.assertFalse(self.t2.hasData())

    def test_read0(self):
        self.assertEqual(self.t1.read(0), b'')


class FieldTestCase(unittest.TestCase):
    def setUp(self):
        defaultTO = 0.5
        self.t1, self.t2 = transportPair(defaultTimeout=defaultTO)

    def tearDown(self):
        self.t1.close()
        self.t2.close()

    def _test_FD(self, fd, data, badData):
        field = packet.Field(fd)
        field.value = data
        field.write(self.t1)
        field.value = badData
        field.read(self.t2)
        if isinstance(data, float):
            self.assertAlmostEqual(data, field.value)
        else:
            self.assertEqual(data, field.value)

    def test_FixedLengthFD(self):
        data = b'Test data'
        badData = b'Bad data!'
        self.assertEqual(len(data), len(badData))
        fd = packet.FixedLengthFD("Test", len(data))
        self._test_FD(fd, data, badData)

    def test_VarLengthFD(self):
        data = b'Test data'
        badData = b'Nope'
        fd = packet.VarLengthFD("Test", 1)
        self._test_FD(fd, data, badData)

    def test_IntFD(self):
        data = 123
        badData = 456
        fd = packet.IntFD("Test", 2)
        self._test_FD(fd, data, badData)
        data = -123
        badData = -456
        fd = packet.IntFD("Test", 2).setSigned(True)
        self._test_FD(fd, data, badData)

    def test_FloatFD(self):
        data = 1.23
        badData = 4.56
        fd = packet.FloatFD("Test")
        self._test_FD(fd, data, badData)

    def test_StructFD(self):
        format = ">?i3s"
        data = (True, 1, b"Hi!")
        badData = (False, 7, b"Bye")
        fd = packet.StructFD("Test", format)
        self._test_FD(fd, data, badData)

    # TODO: Other FDs


class TestPacket(packet.Packet):
    __structure__ = (packet.IntFD("TPID", 1).setDefault(17), packet.StringFD("TPVAL", 1).setMaxLength(32))


class PacketTestCase(unittest.TestCase):
    def setUp(self):
        defaultTO = 0.5
        self.t1, self.t2 = transportPair(defaultTimeout=defaultTO)

    def tearDown(self):
        self.t1.close()
        self.t2.close()

    def test_normalExchange(self):
        sp = TestPacket(TPVAL="Hello there")
        sp.write(self.t1)
        rp = TestPacket()
        rp.read(self.t2)
        self.assertEqual(sp.TPID, rp.TPID)
        self.assertEqual(sp.TPVAL, rp.TPVAL)

    def test_isComplete(self):
        p = TestPacket(TPVAL="Hello there")
        self.assertTrue(p.isComplete())
        p = TestPacket()
        self.assertFalse(p.isComplete())

    def test_update(self):
        data = "Something"
        p = TestPacket()
        self.assertNotEqual(p.TPVAL, data)
        p.update({"TPVAL": data})
        self.assertEqual(p.TPVAL, data)

    def test_hasField(self):
        p = TestPacket()
        self.assertTrue(p.hasField("TPID"))
        self.assertFalse(p.hasField("Non-existent field"))

    # TODO: Probably more tests, but I'm lazy


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    unittest.main()
