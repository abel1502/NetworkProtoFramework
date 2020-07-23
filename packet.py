import logging
from typing import *
import abc
import struct
import transport


class Serializable(object, metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def write(self, tp):
        """
        :type tp: transport.Transport
        :rtype: None
        """
        pass

    @abc.abstractmethod
    def read(self, tp):
        """
        :type tp: transport.Transport
        :rtype: None
        """
        pass


class Packet(Serializable, metaclass=abc.ABCMeta):
    pass


class Structure(object):
    pass


class Field(Serializable):
    def __init__(self, definition):
        """
        :type definition: FieldDef
        """
        self.definition = definition
        self._value = None
        self.value = self.definition.default

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, val):
        self._value = val

    def write(self, tp):
        self.definition.write(self.value, tp)

    def read(self, tp):
        self.value = self.definition.read(tp)


class FieldDef(object, metaclass=abc.ABCMeta):
    def __init__(self, name):
        self.name = name
        self.default = None

    # Such 'transparent configurators' should be implemented for settings, which the user is allowed not to set
    # (Hopefully that's adequate English...)
    def setDefault(self, default):
        self.default = default
        return self

    @abc.abstractmethod
    def write(self, value, tp):
        pass

    @abc.abstractmethod
    def read(self, tp):
        pass


class FixedLengthFD(FieldDef):
    valueType = bytes

    def __init__(self, name, length):
        super().__init__(name)
        assert length >= 0
        self.length = length

    def write(self, value, tp):
        """
        :type value: FixedLengthFD.valueType
        :type tp: transport.Transport
        """
        assert len(value) == self.length
        tp.write(value)

    def read(self, tp):
        """
        :type tp: transport.Transport
        :rtype: FixedLengthFD.valueType
        """
        value = tp.read(self.length)
        return value


class VarLengthFD(FieldDef):
    valueType = bytes

    def __init__(self, name, lengthFieldSize):
        super().__init__(name)
        self.lengthField = IntFD(f"{name}_length", lengthFieldSize)

    def setMinLength(self, minLength):
        self.lengthField.setMin(minLength)
        return self

    def setMaxLength(self, maxLength):
        self.lengthField.setMax(maxLength)
        return self

    def setLengthOrder(self, order):
        self.lengthField.setOrder(order)
        return self

    def write(self, value, tp):
        """
        :type value: VarLengthFD.valueType
        :type tp: transport.Transport
        """
        self.lengthField.write(len(value), tp)
        tp.write(value)

    def read(self, tp):
        """
        :type tp: transport.Transport
        :rtype: VarLengthFD.valueType
        """
        length = self.lengthField.read(tp)
        value = tp.read(length)
        return value


class IntFD(FixedLengthFD):
    valueType = int

    def __init__(self, name, length):
        super().__init__(name, length)
        self.min = None
        self.max = None
        self.order = "big"
        self.signed = False

    def setMax(self, maximum):
        self.max = maximum
        return self

    def setMin(self, minimum):
        self.min = minimum
        return self

    def setOrder(self, order):
        # "big" or "little"
        self.order = order
        return self

    def setSigned(self, signed):
        self.signed = signed
        return self

    def write(self, value, tp):
        """
        :type value: IntFD.valueType
        :type tp: transport.Transport
        """
        assert self.min is None or self.min <= value
        assert self.max is None or value < self.max
        super().write(value.to_bytes(self.length, self.order, signed=self.signed), tp)

    def read(self, tp):
        """
        :type tp: transport.Transport
        :rtype: IntFD.valueType
        """
        value = int.from_bytes(super().read(tp), self.order, signed=self.signed)
        assert self.min is None or self.min <= value
        assert self.max is None or value < self.max
        return value


class FloatFD(FixedLengthFD):
    valueType = float

    def __init__(self, name):
        super().__init__(name, 4)

    def write(self, value, tp):
        """
        :type value: FloatFD.valueType
        :type tp: transport.Transport
        """
        super().write(struct.pack(">f", value), tp)

    def read(self, tp):
        """
        :type tp: transport.Transport
        :rtype: FloatFD.valueType
        """
        value, = struct.unpack(">f", super().read(tp))
        return value


class StructFD(FixedLengthFD):
    valueType = tuple

    def __init__(self, name, structDef):
        if isinstance(structDef, str):
            structDef = struct.Struct(structDef)
        super().__init__(name, structDef.size)
        self.struct = structDef

    def write(self, value, tp):
        """
        :type value: StructFD.valueType
        :type tp: transport.Transport
        """
        super().write(self.struct.pack(*value), tp)

    def read(self, tp):
        """
        :type tp: transport.Transport
        :rtype: StructFD.valueType
        """
        value = self.struct.unpack(super().read(tp))
        return value


# class PaddedFixedFD(FixedLengthFD):
#     valueType = bytes