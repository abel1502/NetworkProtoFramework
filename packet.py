import logging
from typing import *
import abc
import struct
import collections
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

    def checkValue(self, value):
        return True


class FixedLengthFD(FieldDef):
    valueType = bytes

    def __init__(self, name, length):
        super().__init__(name)
        assert length >= 0
        self.length = length

    def write(self, value, tp):
        """
        :type value: bytes
        :type tp: transport.Transport
        """
        assert self.checkValue(value)
        tp.write(value)

    def read(self, tp):
        """
        :type tp: transport.Transport
        :rtype: bytes
        """
        value = tp.read(self.length)
        assert self.checkValue(value)
        return value

    def checkValue(self, value):
        return isinstance(value, (bytes, bytearray)) and len(value) == self.length


class VarLengthFD(FieldDef):
    def __init__(self, name, lengthFieldSize):
        super().__init__(name)
        self.lengthFD = IntFD(f"{name}_length", lengthFieldSize)

    def setMinLength(self, minLength):
        self.lengthFD.setMin(minLength)
        return self

    def setMaxLength(self, maxLength):
        self.lengthFD.setMax(maxLength)
        return self

    def setLengthOrder(self, order):
        self.lengthFD.setOrder(order)
        return self

    def write(self, value, tp):
        """
        :type value: bytes
        :type tp: transport.Transport
        """
        assert self.checkValue(value)
        self.lengthFD.write(len(value), tp)
        tp.write(value)

    def read(self, tp):
        """
        :type tp: transport.Transport
        :rtype: bytes
        """
        length = self.lengthFD.read(tp)
        value = tp.read(length)
        assert self.checkValue(value)
        return value

    def checkValue(self, value):
        return isinstance(value, (bytes, bytearray))


class IntFD(FieldDef):
    def __init__(self, name, length):
        super().__init__(name)
        self.innerFD = FixedLengthFD(f"{name}_inner", length)
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
        :type value: int
        :type tp: transport.Transport
        """
        assert self.checkValue(value)
        self.innerFD.write(value.to_bytes(self.innerFD.length, self.order, signed=self.signed), tp)

    def read(self, tp):
        """
        :type tp: transport.Transport
        :rtype: int
        """
        value = int.from_bytes(self.innerFD.read(tp), self.order, signed=self.signed)
        assert self.checkValue(value)
        return value

    def checkValue(self, value):
        return isinstance(value, int) and (self.min is None or self.min <= value) and (self.max is None or value < self.max)


class FloatFD(FieldDef):
    def __init__(self, name):
        super().__init__(name)
        self.innerFD = FixedLengthFD(f"{name}_inner", 4)

    def write(self, value, tp):
        """
        :type value: float
        :type tp: transport.Transport
        """
        assert self.checkValue(value)
        self.innerFD.write(struct.pack(">f", value), tp)

    def read(self, tp):
        """
        :type tp: transport.Transport
        :rtype: float
        """
        value, = struct.unpack(">f", self.innerFD.read(tp))
        assert self.checkValue(value)
        return value

    def checkValue(self, value):
        return isinstance(value, float)


class StructFD(FieldDef):
    def __init__(self, name, structDef):
        super().__init__(name)
        if isinstance(structDef, str):
            structDef = struct.Struct(structDef)
        self.struct = structDef
        self.innerFD = FixedLengthFD(f"{name}_inner", self.struct.size)

    def write(self, value, tp):
        """
        :type value: tuple
        :type tp: transport.Transport
        """
        assert self.checkValue(value)
        self.innerFD.write(self.struct.pack(*value), tp)

    def read(self, tp):
        """
        :type tp: transport.Transport
        :rtype: tuple
        """
        value = self.struct.unpack(self.innerFD.read(tp))
        assert self.checkValue(value)
        return value

    def checkValue(self, value):
        if not isinstance(value, tuple):
            return False
        try:
            self.struct.pack(*value)
        except struct.error:
            return False
        return True


class SerializableFD(FieldDef):
    def __init__(self, name, packetType):
        super().__init__(name)
        self.packetType = packetType

    def write(self, value, tp):
        """
        :type value: Serializable
        :type tp: transport.Transport
        """
        assert self.checkValue(value)
        value.write(tp)

    def read(self, tp):
        """
        :type tp: transport.Transport
        :rtype: Serializable
        """
        value = self.packetType().read(tp)
        assert self.checkValue(value)
        return value

    def checkValue(self, value):
        return isinstance(value, self.packetType)


class StringFD(FieldDef):
    def __init__(self, name, lengthFieldSize):
        super().__init__(name)
        self.innerFD = VarLengthFD(f"{name}_inner", lengthFieldSize)
        self.encoding = "utf-8"

    def setMinLength(self, minLength):
        self.innerFD.setMinLength(minLength)
        return self

    def setMaxLength(self, maxLength):
        self.innerFD.setMaxLength(maxLength)
        return self

    def setLengthOrder(self, order):
        self.innerFD.setLengthOrder(order)
        return self

    def setEncoding(self, encoding):
        self.encoding = encoding
        return self

    def write(self, value, tp):
        """
        :type value: str
        :type tp: transport.Transport
        """
        assert self.checkValue(value)
        self.innerFD.write(value.encode(self.encoding), tp)

    def read(self, tp):
        """
        :type tp: transport.Transport
        :rtype: str
        """
        value = self.innerFD.read(tp).decode(self.encoding)
        assert self.checkValue(value)
        return value

    def checkValue(self, value):
        return isinstance(value, str)


# class PaddedFixedFD(FixedLengthFD):
#     valueType = bytes


# TODO: Discriminated union FD?; ...


class Packet(Serializable, metaclass=abc.ABCMeta):
    __structure__ = tuple()

    def __init__(self, **fieldValues):
        self.__fields__ = collections.OrderedDict()
        for fd in self.__structure__:
            assert fd.name not in self.__fields__
            self.__fields__[fd.name] = Field(fd)
        self.update(fieldValues)

    def write(self, tp):
        assert self.isComplete()
        for field in self.__fields__.values():
            field.write(tp)

    def read(self, tp):
        for field in self.__fields__.values():
            field.read(tp)

    def update(self, fieldsDict):
        for name, value in fieldsDict.items():
            self.setField(name, value)

    def isComplete(self):
        for field in self.__fields__.values():
            if field.value is None:
                return False
        return True

    def hasField(self, name):
        # Not hasattr because that calls getattr internally
        return "__fields__" in dir(self) and name in self.__fields__

    def getField(self, name, asValue=True):
        field = self.__fields__[name]
        if not asValue:
            return field
        return field.value

    def setField(self, name, value):
        self.__fields__[name].value = value

    # This is only called for non-present attributes, so I only handle fields here
    def __getattr__(self, name):
        if self.hasField(name):
            return self.getField(name)
        raise AttributeError

    def __setattr__(self, name, value):
        if self.hasField(name):
            self.setField(name, value)
        else:
            super().__setattr__(name, value)

