from __future__ import annotations
from dataclasses import dataclass, field

import bpy
from struct import pack
from copy import copy

from ..utility import radian_to_sm64_degree
from ..sm64_function_map import func_map

from ...utility import (
    PluginError,
    CData,
    toAlnum,
    encodeSegmentedAddr,
    writeVectorToShorts,
    convertFloatToShort,
    writeEulerVectorToShorts,
    convertEulerFloatToShort,
    join_c_args,
)
from ...f3d.f3d_bleed import BleedGraphics

from .constants import nodeGroupCmds, drawLayerNames, geoNodeRotateOrder, GeoNodeEnum


def get_draw_layer_enum(draw_layer: int | str):
    layer = draw_layer
    try:
        # Cast draw layer to int so it can be mapped to a name
        layer = int(draw_layer)
    except ValueError:
        pass
    return drawLayerNames.get(layer, str(draw_layer))


def append_function_address(command_byte_array: bytearray, function: str):
    try:
        command_byte_array.extend(bytes.fromhex(function))
    except ValueError:
        raise PluginError(f'In geolayout node, could not convert function "{function}" to hexadecimal.')


def address_to_decomp_function(function_or_address: str) -> str:
    """
    Tries to find the argument in the sm64 function map for the current refresh version.
    If one cannot be found, it returns the argument.
    """

    if function_or_address == "":
        raise PluginError("Geolayout node cannot have an empty function name/address.")

    refresh_func_map = func_map[bpy.context.scene.fast64.sm64.refresh_version]
    return refresh_func_map.get(function_or_address.lower(), toAlnum(function_or_address))


class GeolayoutGraph:
    def __init__(self, name):
        self.startGeolayout = Geolayout(name, True)
        # dict of Object : Geolayout
        self.secondaryGeolayouts = {}
        # dict of Geolayout : Geolayout List (which geolayouts are called)
        self.geolayoutCalls = {}
        self.sortedList = []
        self.sortedListGenerated = False

    def checkListSorted(self):
        if not self.sortedListGenerated:
            raise PluginError("Must generate sorted geolayout list first " + "before calling this function.")

    def get_ptr_addresses(self):
        self.checkListSorted()
        addresses = []
        for geolayout in self.sortedList:
            addresses.extend(geolayout.get_ptr_addresses())
        return addresses

    def size(self):
        self.checkListSorted()
        size = 0
        for geolayout in self.sortedList:
            size += geolayout.size()

        return size

    def addGeolayout(self, obj, name):
        geolayout = Geolayout(name, False)
        self.secondaryGeolayouts[obj] = geolayout
        return geolayout

    def addJumpNode(self, parentNode, caller, callee, index=None):
        if index is None:
            parentNode.children.append(TransformNode(JumpNode(True, callee)))
        else:
            parentNode.children.insert(index, TransformNode(JumpNode(True, callee)))
        self.addGeolayoutCall(caller, callee)

    def addGeolayoutCall(self, caller, callee):
        if caller not in self.geolayoutCalls:
            self.geolayoutCalls[caller] = []
        self.geolayoutCalls[caller].append(callee)

    def sortGeolayouts(self, geolayoutList, geolayout, callOrder):
        if geolayout in self.geolayoutCalls:
            for calledGeolayout in self.geolayoutCalls[geolayout]:
                geoIndex = geolayoutList.index(geolayout)
                if calledGeolayout in geolayoutList:
                    callIndex = geolayoutList.index(calledGeolayout)
                    if callIndex < geoIndex:
                        continue
                    raise PluginError("Circular geolayout dependency." + str(callOrder))
                else:
                    geolayoutList.insert(geolayoutList.index(geolayout), calledGeolayout)
                    callOrder = copy(callOrder)
                    callOrder.append(calledGeolayout)
                    self.sortGeolayouts(geolayoutList, calledGeolayout, callOrder)
        return geolayoutList

    def generateSortedList(self):
        self.sortedList = self.sortGeolayouts([self.startGeolayout], self.startGeolayout, [self.startGeolayout])
        self.sortedListGenerated = True

    def set_addr(self, address):
        self.checkListSorted()
        for geolayout in self.sortedList:
            geolayout.startAddress = address
            address += geolayout.size()
            print(geolayout.name + " - " + str(geolayout.startAddress))
        return address

    def to_binary(self, segmentData):
        self.checkListSorted()
        data = bytearray(0)
        for geolayout in self.sortedList:
            data += geolayout.to_binary(segmentData)
        return data

    def save_binary(self, romfile, segmentData):
        for geolayout in self.sortedList:
            geolayout.save_binary(romfile, segmentData)

    def to_c(self):
        data = CData()
        self.checkListSorted()
        data.source = '#include "src/game/envfx_snow.h"\n\n'
        for geolayout in self.sortedList:
            data.append(geolayout.to_c())
        return data

    def toTextDump(self, segmentData):
        self.checkListSorted()
        data = ""
        for geolayout in self.sortedList:
            data += geolayout.toTextDump(segmentData) + "\n"
        return data

    def convertToDynamic(self):
        self.checkListSorted()
        for geolayout in self.sortedList:
            for node in geolayout.nodes:
                node.convertToDynamic()

    def getDrawLayers(self):
        drawLayers = self.startGeolayout.getDrawLayers()
        for obj, geolayout in self.secondaryGeolayouts.items():
            drawLayers |= geolayout.getDrawLayers()

        return drawLayers


class Geolayout:
    def __init__(self, name, isStartGeo):
        self.nodes = []
        self.name = toAlnum(name)
        self.startAddress = 0
        self.isStartGeo = isStartGeo

    def size(self):
        size = 4  # end command
        for node in self.nodes:
            size += node.size()
        return size

    def get_ptr_addresses(self):
        address = self.startAddress
        addresses = []
        for node in self.nodes:
            address, ptrs = node.get_ptr_addresses(address)
            addresses.extend(ptrs)
        return addresses

    def to_binary(self, segmentData):
        endCmd = GeoNodeEnum.END if self.isStartGeo else GeoNodeEnum.RETURN
        data = bytearray(0)
        for node in self.nodes:
            data += node.to_binary(segmentData)
        data += bytearray([endCmd, 0x00, 0x00, 0x00])
        return data

    def save_binary(self, romfile, segmentData):
        romfile.seek(self.startAddress)
        romfile.write(self.to_binary(segmentData))

    def to_c(self):
        endCmd = "GEO_END" if self.isStartGeo else "GEO_RETURN"
        data = CData()
        data.header = "extern const GeoLayout " + self.name + "[];\n"
        data.source = "const GeoLayout " + self.name + "[] = {\n"
        for node in self.nodes:
            data.source += node.to_c(1)
        data.source += "\t" + endCmd + "(),\n"
        data.source += "};\n"
        return data

    def toTextDump(self, segmentData):
        endCmd = "01" if self.isStartGeo else "03"
        data = ""
        for node in self.nodes:
            data += node.toTextDump(0, segmentData)
        data += endCmd + " 00 00 00\n"
        return data

    def getDrawLayers(self):
        drawLayers = set()
        for node in self.nodes:
            drawLayers |= node.getDrawLayers()
        return drawLayers


class GeoLayoutBleed(BleedGraphics):
    def bleed_geo_layout_graph(self, fModel: FModel, geo_layout_graph: GeolayoutGraph, use_rooms: bool = False):
        last_materials = dict()  # last used material should be kept track of per layer

        def walk(node, last_materials):
            base_node = node.node
            if type(base_node) == JumpNode:
                if base_node.geolayout:
                    for node in base_node.geolayout.nodes:
                        last_materials = (
                            walk(node, last_materials if not use_rooms else dict()) if not use_rooms else dict()
                        )
                else:
                    last_materials = dict()
            fMesh = getattr(base_node, "fMesh", None)
            if fMesh:
                cmd_list = fMesh.drawMatOverrides.get(base_node.override_hash, None) or fMesh.draw
                lastMat = last_materials.get(base_node.drawLayer, None)
                default_render_mode = fModel.getRenderMode(base_node.drawLayer)
                lastMat = self.bleed_fmesh(fModel.f3d, fMesh, lastMat, cmd_list, default_render_mode)
                # if the mesh has culling, it can be culled, and create invalid combinations of f3d to represent the current full DL
                if fMesh.cullVertexList:
                    last_materials[base_node.drawLayer] = None
                else:
                    last_materials[base_node.drawLayer] = lastMat
            # don't carry over lastmat if it is a switch node or geo asm node
            if type(base_node) in [SwitchNode, FunctionNode, DefineNode]:
                last_materials = dict()
            for child in node.children:
                last_materials = walk(child, last_materials)
            return last_materials

        for node in geo_layout_graph.startGeolayout.nodes:
            last_materials = walk(node, last_materials)
        self.clear_gfx_lists(fModel)


class TransformNode:
    def __init__(self, node):
        self.node = node
        self.children = []
        self.parent = None
        self.skinned = False
        self.skinnedWithoutDL = False

    def convertToDynamic(self):
        if self.node.has_dl:
            funcNode = FunctionNode(self.node.DLmicrocode.name, self.node.drawLayer)

            if isinstance(self.node, DisplayListNode):
                self.node = funcNode
            else:
                self.node.has_dl = False
                transformNode = TransformNode(funcNode)
                self.children.insert(0, transformNode)

        for child in self.children:
            child.convertToDynamic()

    def get_ptr_addresses(self, address):
        addresses = []
        if self.node is not None:
            if type(self.node) in DLNodes:
                for offset in self.node.get_ptr_offsets():
                    addresses.append(address + offset)
            else:
                addresses = []
            address += self.node.size()
        if len(self.children) > 0:
            address += 4
            for node in self.children:
                address, ptrs = node.get_ptr_addresses(address)
                addresses.extend(ptrs)
            address += 4
        return address, addresses

    def size(self):
        size = self.node.size() if self.node is not None else 0
        if len(self.children) > 0 and type(self.node) in nodeGroupClasses:
            size += 8  # node open/close
            for child in self.children:
                size += child.size()

        return size

    # Function commands usually effect the following command, so it is similar
    # to a parent child relationship.
    def to_binary(self, segmentData):
        if self.node is not None:
            data = self.node.to_binary(segmentData)
        else:
            data = bytearray(0)
        if len(self.children) > 0:
            if type(self.node) is FunctionNode:
                raise PluginError("An FunctionNode cannot have children.")

            if data[0] in nodeGroupCmds:
                data.extend(bytearray([GeoNodeEnum.OPEN, 0x00, 0x00, 0x00]))
            for child in self.children:
                data.extend(child.to_binary(segmentData))
            if data[0] in nodeGroupCmds:
                data.extend(bytearray([GeoNodeEnum.CLOSE, 0x00, 0x00, 0x00]))
        elif type(self.node) is SwitchNode:
            raise PluginError("A switch bone must have at least one child bone.")
        return data

    def to_c(self, depth):
        if self.node is not None:
            nodeC = self.node.to_c()
            if nodeC is not None:  # Should only be the case for DisplayListNode with no DL
                data = depth * "\t" + self.node.to_c() + "\n"
            else:
                data = ""
        else:
            data = ""
        if len(self.children) > 0:
            if type(self.node) in nodeGroupClasses:
                data += depth * "\t" + "GEO_OPEN_NODE(),\n"
            for child in self.children:
                data += child.to_c(depth + (1 if type(self.node) in nodeGroupClasses else 0))
            if type(self.node) in nodeGroupClasses:
                data += depth * "\t" + "GEO_CLOSE_NODE(),\n"
        elif type(self.node) is SwitchNode:
            raise PluginError("A switch bone must have at least one child bone.")
        return data

    def toTextDump(self, nodeLevel, segmentData):
        data = ""
        if self.node is not None:
            command = self.node.to_binary(segmentData)
        else:
            command = bytearray(0)

        data += "\t" * nodeLevel
        for byteVal in command:
            data += format(byteVal, "02X") + " "
        data += "\n"

        if len(self.children) > 0:
            if len(command) == 0 or command[0] in nodeGroupCmds:
                data += "\t" * nodeLevel + "04 00 00 00\n"
            for child in self.children:
                data += child.toTextDump(nodeLevel + 1, segmentData)
            if len(command) == 0 or command[0] in nodeGroupCmds:
                data += "\t" * nodeLevel + "05 00 00 00\n"
        elif type(self.node) is SwitchNode:
            raise PluginError("A switch bone must have at least one child bone.")
        return data

    def getDrawLayers(self):
        if self.node is not None and self.node.has_dl:
            drawLayers = set([self.node.drawLayer])
        else:
            drawLayers = set()
        for child in self.children:
            if hasattr(child, "getDrawLayers"):  # not every child will have draw layers (e.g. GEO_ASM)
                drawLayers |= child.getDrawLayers()
        return drawLayers


@dataclass
class GeoNode:
    name: str = "Unnamed"
    has_dl: bool = False

    def get_ptr_offsets(self):
        return []

    def raise_error(self, error: str):
        raise PluginError(f'Geo node command "{self.name}" ({str(self.__class__)}) {error}')

    def size(self):
        self.raise_error("has no size implementation.")

    def to_binary(self, segmentData):
        self.raise_error("has no binary export implementation.")

    def to_c(self):
        self.raise_error("has no c export implementation.")


class BaseDisplayListNode(GeoNode):
    """Base displaylist node with common helper functions dealing with displaylists"""

    dl_ext = "WITH_DL"  # add dl_ext to geo command if command has a displaylist

    def get_dl_address(self):
        if self.dlRef:
            return int(self.dlRef)
        if self.has_dl and self.DLmicrocode:
            return self.DLmicrocode.startAddress
        return None

    def get_dl_name(self):
        if self.dlRef:
            return self.dlRef
        if self.has_dl:
            if self.DLmicrocode:
                return self.DLmicrocode.name
        return "NULL"

    def get_c_func_macro(self, base_cmd: str):
        return f"{base_cmd}_{self.dl_ext}" if self.has_dl else base_cmd

    def c_func_macro(self, base_cmd: str, *args: str):
        """
        Supply base command and all arguments for command.
        if self.has_dl:
                this will add self.dl_ext to the command, and
                adds the name of the displaylist to the end of the command
        Example return: 'GEO_YOUR_COMMAND_WITH_DL(arg, arg2),'
        """
        all_args = list(args)
        if self.has_dl:
            all_args.append(self.get_dl_name())
        return f'{self.get_c_func_macro(base_cmd)}({", ".join(all_args)}),'


class SwitchOverrideNode:
    def __init__(self, material, specificMat, drawLayer, overrideType, texDimensions):
        self.material = material
        self.specificMat = specificMat
        self.drawLayer = drawLayer
        self.overrideType = overrideType
        self.texDimensions = texDimensions  # None implies a draw layer override


class JumpNode(GeoNode):
    def __init__(self, storeReturn, geolayout, geoRef: str = None):
        self.geolayout = geolayout
        self.storeReturn = storeReturn
        self.geoRef = geoRef

    def size(self):
        return 8

    def get_ptr_offsets(self):
        return [4]

    def to_binary(self, segmentData):
        if segmentData is not None:
            address = self.geoRef or self.geolayout.startAddress
            startAddress = encodeSegmentedAddr(address, segmentData)
        else:
            startAddress = bytearray([0x00] * 4)
        command = bytearray([GeoNodeEnum.BRANCH, 0x01 if self.storeReturn else 0x00, 0x00, 0x00])
        command.extend(startAddress)
        return command

    def to_c(self):
        geo_name = self.geoRef or self.geolayout.name
        return "GEO_BRANCH(" + ("1, " if self.storeReturn else "0, ") + geo_name + "),"


# We add Function commands to nonDeformTransformData because any skinned
# 0x15 commands should go before them, as they are usually preceding
# an empty transform command (of which they modify?)
class FunctionNode(GeoNode):
    def __init__(self, function: str, parameter: str):
        self.function = function
        self.parameter = parameter

        self.name = "Function"

    def size(self):
        return 8

    def to_binary(self, segmentData):
        command = bytearray([GeoNodeEnum.CALL_ASM, 0x00])
        parameter = int(self.parameter)
        command.extend(parameter.to_bytes(2, "big", signed=True))
        append_function_address(command, self.function)
        return command

    def to_c(self):
        args = [str(self.parameter), address_to_decomp_function(self.function)]
        return f"GEO_ASM({join_c_args(args)}),"


class HeldObjectNode(GeoNode):
    def __init__(self, parameter: str, function: str, translate: list[float]):
        self.parameter = parameter
        self.function = function
        self.translate = translate

        self.name = "Held Object"

    def size(self):
        return 12

    def to_binary(self, segmentData):
        command = bytearray([GeoNodeEnum.HELD_OBJECT])
        parameter = int(self.parameter)
        command.extend(int.to_bytes(parameter, 2, "big", signed=True))
        command.extend(bytearray([0x00] * 6))
        writeVectorToShorts(command, 2, self.translate)
        append_function_address(command, self.function)
        return command

    def to_c(self):
        args = [
            self.parameter,
            str(convertFloatToShort(self.translate[0])),
            str(convertFloatToShort(self.translate[1])),
            str(convertFloatToShort(self.translate[2])),
            address_to_decomp_function(self.function),
        ]
        return f"GEO_HELD_OBJECT({join_c_args(args)}),"


class StartNode(GeoNode):
    def __init__(self):
        self.name = "Start"

    def size(self):
        return 4

    def to_binary(self, segmentData):
        command = bytearray([GeoNodeEnum.START, 0x00, 0x00, 0x00])
        return command

    def to_c(self):
        return "GEO_NODE_START(),"


class EndNode(GeoNode):
    def __init__(self):
        self.name = "End"

    def size(self):
        return 4

    def to_binary(self, segmentData):
        command = bytearray([GeoNodeEnum.END, 0x00, 0x00, 0x00])
        return command

    def to_c(self):
        return "GEO_END(),"


# Geolayout node hierarchy is first generated without material/draw layer
# override options, but with material override DL's being generated.
# Afterward, for each switch node the node hierarchy is duplicated and
# the correct diplsay lists are added.
class SwitchNode(GeoNode):
    def __init__(self):
        self.name = "Switch"

    def __init__(self, function, func_param, name):
        self.function = function
        self.defaultCase = func_param
        self.switch_name = name

    def size(self):
        return 8

    def to_binary(self, segmentData):
        command = bytearray([GeoNodeEnum.SWITCH, 0x00])
        defaultCase = int(self.defaultCase)
        command.extend(defaultCase.to_bytes(2, "big", signed=True))
        append_function_address(command, self.function)
        return command

    def to_c(self):
        args = [str(self.defaultCase), address_to_decomp_function(self.function)]
        return f"GEO_SWITCH_CASE({join_c_args(args)}),"

class DefineNode(GeoNode):
    def __init__(self):
        self.name = "Define Options"


class TranslateRotateNode(BaseDisplayListNode):
    def __init__(self, drawLayer, has_dl, translate, rotate, dlRef: str = None):
        self.drawLayer = drawLayer
        self.has_dl = has_dl

        self.translate = translate
        self.rotate = rotate

        self.fMesh = None
        self.DLmicrocode = None
        self.dlRef = dlRef
        # exists to get the override DL from an fMesh
        self.override_hash = None

        self.name = "Translate Rotate"

    def get_ptr_offsets(self):
        if self.has_dl:
            return [16]
        return []

    def size(self):
        size = 16
        if self.has_dl:
            size += 4
        return size

    def to_binary(self, segmentData):
        # TODO: Update this
        params = ((1 if self.has_dl else 0) << 7) & (self.fieldLayout << 4) | int(self.drawLayer)

        start_address = self.get_dl_address()

        command = bytearray([GeoNodeEnum.TRANSLATE_ROTATE, params])

        command.extend(bytearray([0x00] * 14))
        writeVectorToShorts(command, 4, self.translate)
        writeEulerVectorToShorts(command, 10, self.rotate.to_euler(geoNodeRotateOrder))

        if start_address:
            if segmentData is not None:
                command.extend(encodeSegmentedAddr(start_address, segmentData))
            else:
                command.extend(bytearray([0x00] * 4))
        return command

    def to_c(self):
        return self.c_func_macro(
            "GEO_TRANSLATE_ROTATE",
            get_draw_layer_enum(self.drawLayer),
            str(convertFloatToShort(self.translate[0])),
            str(convertFloatToShort(self.translate[1])),
            str(convertFloatToShort(self.translate[2])),
            str(convertEulerFloatToShort(self.rotate.to_euler(geoNodeRotateOrder)[0])),
            str(convertEulerFloatToShort(self.rotate.to_euler(geoNodeRotateOrder)[1])),
            str(convertEulerFloatToShort(self.rotate.to_euler(geoNodeRotateOrder)[2])),
        )


class TranslateNode(BaseDisplayListNode):
    def __init__(self, drawLayer, useDeform, translate, dlRef: str = None):
        self.drawLayer = drawLayer
        self.has_dl = useDeform
        self.translate = translate
        self.fMesh = None
        self.DLmicrocode = None
        self.dlRef = dlRef
        # exists to get the override DL from an fMesh
        self.override_hash = None

        self.name = "Translate"

    def get_ptr_offsets(self):
        return [8] if self.has_dl else []

    def size(self):
        return 12 if self.has_dl else 8

    def to_binary(self, segmentData):
        params = ((1 if self.has_dl else 0) << 7) | int(self.drawLayer)
        command = bytearray([GeoNodeEnum.TRANSLATE, params])
        command.extend(bytearray([0x00] * 6))
        writeVectorToShorts(command, 2, self.translate)

        if self.has_dl:
            start_address = self.get_dl_address()
            if segmentData is not None:
                command.extend(encodeSegmentedAddr(start_address, segmentData))
            else:
                command.extend(bytearray([0x00] * 4))
        return command

    def to_c(self):
        return self.c_func_macro(
            "GEO_TRANSLATE_NODE",
            get_draw_layer_enum(self.drawLayer),
            str(convertFloatToShort(self.translate[0])),
            str(convertFloatToShort(self.translate[1])),
            str(convertFloatToShort(self.translate[2])),
        )


class RotateNode(BaseDisplayListNode):
    def __init__(self, drawLayer, has_dl, rotate, dlRef: str = None):
        # In the case for automatically inserting rotate nodes between
        # 0x13 bones.

        self.drawLayer = drawLayer
        self.has_dl = has_dl
        self.rotate = rotate
        self.fMesh = None
        self.DLmicrocode = None
        self.dlRef = dlRef
        # exists to get the override DL from an fMesh
        self.override_hash = None

        self.name = "Rotate"

    def get_ptr_offsets(self):
        return [8] if self.has_dl else []

    def size(self):
        return 12 if self.has_dl else 8

    def to_binary(self, segmentData):
        params = ((1 if self.has_dl else 0) << 7) | int(self.drawLayer)
        command = bytearray([GeoNodeEnum.ROTATE, params])
        command.extend(bytearray([0x00] * 6))
        writeEulerVectorToShorts(command, 2, self.rotate.to_euler(geoNodeRotateOrder))
        if self.has_dl:
            start_address = self.get_dl_address()
            if segmentData is not None:
                command.extend(encodeSegmentedAddr(start_address, segmentData))
            else:
                command.extend(bytearray([0x00] * 4))
        return command

    def to_c(self):
        return self.c_func_macro(
            "GEO_ROTATION_NODE",
            get_draw_layer_enum(self.drawLayer),
            str(convertEulerFloatToShort(self.rotate.to_euler(geoNodeRotateOrder)[0])),
            str(convertEulerFloatToShort(self.rotate.to_euler(geoNodeRotateOrder)[1])),
            str(convertEulerFloatToShort(self.rotate.to_euler(geoNodeRotateOrder)[2])),
        )


class BillboardNode(BaseDisplayListNode):
    dl_ext = "AND_DL"

    def __init__(self, drawLayer, has_dl, translate, dlRef: str = None):
        self.drawLayer = drawLayer
        self.has_dl = has_dl
        self.translate = translate
        self.fMesh = None
        self.DLmicrocode = None
        self.dlRef = dlRef
        # exists to get the override DL from an fMesh
        self.override_hash = None

        self.name = "Billboard"

    def get_ptr_offsets(self):
        return [8] if self.has_dl else []

    def size(self):
        return 12 if self.has_dl else 8

    def to_binary(self, segmentData):
        params = ((1 if self.has_dl else 0) << 7) | int(self.drawLayer)
        command = bytearray([GeoNodeEnum.BILLBOARD, params])
        command.extend(bytearray([0x00] * 6))
        writeVectorToShorts(command, 2, self.translate)
        if self.has_dl:
            start_address = self.get_dl_address()
            if segmentData is not None:
                command.extend(encodeSegmentedAddr(start_address, segmentData))
            else:
                command.extend(bytearray([0x00] * 4))
        return command

    def to_c(self):
        return self.c_func_macro(
            "GEO_BILLBOARD_WITH_PARAMS",
            get_draw_layer_enum(self.drawLayer),
            str(convertFloatToShort(self.translate[0])),
            str(convertFloatToShort(self.translate[1])),
            str(convertFloatToShort(self.translate[2])),
        )


class DisplayListNode(BaseDisplayListNode):
    def __init__(self, drawLayer, dlRef: str = None):
        self.drawLayer = drawLayer
        self.has_dl = True
        self.fMesh = None
        self.DLmicrocode = None
        self.dlRef = dlRef
        # exists to get the override DL from an fMesh
        self.override_hash = None

        self.name = "Display List"

    def get_ptr_offsets(self):
        return [4]

    def size(self):
        return 8

    def to_binary(self, segmentData):
        command = bytearray([GeoNodeEnum.LOAD_DL, int(self.drawLayer), 0x00, 0x00])
        start_address = self.get_dl_address()
        if start_address and segmentData is not None:
            command.extend(encodeSegmentedAddr(start_address, segmentData))
        else:
            command.extend(bytearray([0x00] * 4))
        return command

    def to_c(self):
        if not self.has_dl:
            return None
        args = [get_draw_layer_enum(self.drawLayer), self.get_dl_name()]
        return f"GEO_DISPLAY_LIST({join_c_args(args)}),"


shadow_enum_to_value = {
    "SHADOW_CIRCLE_9_VERTS": 0,
    "SHADOW_CIRCLE_4_VERTS": 1,
    "SHADOW_CIRCLE_4_VERTS_FLAT_UNUSED": 2,
    "SHADOW_SQUARE_PERMANENT": 10,
    "SHADOW_SQUARE_SCALABLE": 11,
    "SHADOW_SQUARE_TOGGLABLE": 12,
    "SHADOW_RECTANGLE_HARDCODED_OFFSET": 50,
    "SHADOW_CIRCLE_PLAYER": 99,
}


class ShadowNode(GeoNode):
    def __init__(self, shadow_type: str, shadow_solidity, shadow_scale):
        self.shadowType = shadow_type
        self.shadowSolidity = int(round(shadow_solidity * 0xFF))
        self.shadowScale = shadow_scale

        self.name = "Shadow"

    def size(self):
        return 8

    def to_binary(self, segmentData):
        command = bytearray([GeoNodeEnum.START_W_SHADOW, 0x00])
        command.extend(shadow_enum_to_value[self.shadowType].to_bytes(2, "big"))
        command.extend(self.shadowSolidity.to_bytes(2, "big"))
        command.extend(self.shadowScale.to_bytes(2, "big"))
        return command

    def to_c(self):
        args = [str(self.shadowType), str(self.shadowSolidity), str(self.shadowScale)]
        return f"GEO_SHADOW({join_c_args(args)}),"


class ScaleNode(BaseDisplayListNode):
    def __init__(self, drawLayer, geo_scale, use_deform, dlRef: str = None):
        self.drawLayer = drawLayer
        self.scaleValue = geo_scale
        self.has_dl = use_deform
        self.fMesh = None
        self.DLmicrocode = None
        self.dlRef = dlRef
        # exists to get the override DL from an fMesh
        self.override_hash = None

        self.name = "Scale"

    def get_ptr_offsets(self):
        return [8] if self.has_dl else []

    def size(self):
        return 12 if self.has_dl else 8

    def to_binary(self, segmentData):
        params = ((1 if self.has_dl else 0) << 7) | int(self.drawLayer)
        command = bytearray([GeoNodeEnum.SCALE, params, 0x00, 0x00])
        command.extend(int(self.scaleValue * 0x10000).to_bytes(4, "big"))
        if self.has_dl:
            if segmentData is not None:
                command.extend(encodeSegmentedAddr(self.get_dl_address(), segmentData))
            else:
                command.extend(bytearray([0x00] * 4))
        return command

    def to_c(self):
        return self.c_func_macro(
            "GEO_SCALE", get_draw_layer_enum(self.drawLayer), str(int(round(self.scaleValue * 0x10000)))
        )


class StartRenderAreaNode(GeoNode):
    def __init__(self, cullingRadius: int):
        self.cullingRadius = cullingRadius

        self.name = "Culling Radius"

    def size(self):
        return 4

    def to_binary(self, segmentData):
        command = bytearray([GeoNodeEnum.START_W_RENDERAREA, 0x00])
        command.extend(self.cullingRadius.to_bytes(2, "big"))
        return command

    def to_c(self):
        return f"GEO_CULLING_RADIUS({str(self.cullingRadius)}),"


class RenderRangeNode(GeoNode):
    def __init__(self, minDist, maxDist):
        self.minDist = minDist
        self.maxDist = maxDist

        self.name = "Render Range"

    def size(self):
        return 8

    def to_binary(self, segmentData):
        command = bytearray([GeoNodeEnum.SET_RENDER_RANGE, 0x00, 0x00, 0x00])
        command.extend(convertFloatToShort(self.minDist).to_bytes(2, "big"))
        command.extend(convertFloatToShort(self.maxDist).to_bytes(2, "big"))
        return command

    def to_c(self):
        minDist = convertFloatToShort(self.minDist)
        maxDist = convertFloatToShort(self.maxDist)
        return "GEO_RENDER_RANGE(" + str(minDist) + ", " + str(maxDist) + "),"


class DisplayListWithOffsetNode(BaseDisplayListNode):
    def __init__(self, drawLayer, use_deform, translate, dlRef: str = None):
        self.drawLayer = drawLayer
        self.has_dl = use_deform
        self.translate = translate
        self.fMesh = None
        self.DLmicrocode = None
        self.dlRef = dlRef
        # exists to get the override DL from an fMesh
        self.override_hash = None

        self.name = "Display List With Offset"

    def size(self):
        return 12

    def get_ptr_offsets(self):
        return [8] if self.has_dl else []

    def to_binary(self, segmentData):
        command = bytearray([GeoNodeEnum.LOAD_DL_W_OFFSET, int(self.drawLayer)])
        command.extend(bytearray([0x00] * 6))
        writeVectorToShorts(command, 2, self.translate)
        start_address = self.get_dl_address()
        if start_address is not None and segmentData is not None:
            command.extend(encodeSegmentedAddr(start_address, segmentData))
        else:
            command.extend(bytearray([0x00] * 4))
        return command

    def to_c(self):
        args = [
            get_draw_layer_enum(self.drawLayer),
            str(convertFloatToShort(self.translate[0])),
            str(convertFloatToShort(self.translate[1])),
            str(convertFloatToShort(self.translate[2])),
            self.get_dl_name(),  # This node requires 'NULL' if there is no DL
        ]
        return f"GEO_ANIMATED_PART({join_c_args(args)}),"


class ScreenAreaNode(GeoNode):
    def __init__(self, useDefaults, entryMinus2Count, position, dimensions):
        self.useDefaults = useDefaults
        self.entryMinus2Count = entryMinus2Count
        self.position = position
        self.dimensions = dimensions

        self.name = "Screen Area"

    def size(self):
        return 12

    def to_binary(self, segmentData):
        position = [160, 120] if self.useDefaults else self.position
        dimensions = [160, 120] if self.useDefaults else self.dimensions
        entryMinus2Count = 0xA if self.useDefaults else self.entryMinus2Count
        command = bytearray([GeoNodeEnum.SET_RENDER_AREA, 0x00])
        command.extend(entryMinus2Count.to_bytes(2, "big", signed=False))
        command.extend(position[0].to_bytes(2, "big", signed=True))
        command.extend(position[1].to_bytes(2, "big", signed=True))
        command.extend(dimensions[0].to_bytes(2, "big", signed=True))
        command.extend(dimensions[1].to_bytes(2, "big", signed=True))
        return command

    def to_c(self):
        if self.useDefaults:
            return (
                "GEO_NODE_SCREEN_AREA(10, " + "SCREEN_WIDTH/2, SCREEN_HEIGHT/2, " + "SCREEN_WIDTH/2, SCREEN_HEIGHT/2),"
            )
        else:
            return (
                "GEO_NODE_SCREEN_AREA("
                + str(self.entryMinus2Count)
                + ", "
                + str(self.position[0])
                + ", "
                + str(self.position[1])
                + ", "
                + str(self.dimensions[0])
                + ", "
                + str(self.dimensions[1])
                + "),"
            )


class OrthoNode(GeoNode):
    def __init__(self, scale):
        self.scale = scale
        self.name = "Ortho"

    def size(self):
        return 4

    def to_binary(self, segmentData):
        command = bytearray([GeoNodeEnum.SET_ORTHO, 0x00])
        # FIX: This should be f32.
        command.extend(bytearray(pack(">f", self.scale)))
        return command

    def to_c(self):
        return "GEO_NODE_ORTHO(" + format(self.scale, ".4f") + "),"


class FrustumNode(GeoNode):
    def __init__(self, fov, near, far):
        self.fov = fov
        self.near = int(round(near))
        self.far = int(round(far))
        self.useFunc = True  # Always use function?

        self.name = "Frustum"

    def size(self):
        return 12 if self.useFunc else 8

    def to_binary(self, segmentData):
        command = bytearray([GeoNodeEnum.SET_CAMERA_FRUSTRUM, 0x01 if self.useFunc else 0x00])
        command.extend(bytearray(pack(">f", self.fov)))
        command.extend(self.near.to_bytes(2, "big", signed=True))  # Conversion?
        command.extend(self.far.to_bytes(2, "big", signed=True))  # Conversion?

        if self.useFunc:
            command.extend(bytes.fromhex("8029AA3C"))
        return command

    def to_c(self):
        if not self.useFunc:
            return "GEO_CAMERA_FRUSTUM(" + format(self.fov, ".4f") + ", " + str(self.near) + ", " + str(self.far) + "),"
        else:
            return (
                "GEO_CAMERA_FRUSTUM_WITH_FUNC("
                + format(self.fov, ".4f")
                + ", "
                + str(self.near)
                + ", "
                + str(self.far)
                + ", geo_camera_fov),"
            )


class ZBufferNode(GeoNode):
    def __init__(self, enable):
        self.enable = enable

        self.name = "Z Buffer"

    def size(self):
        return 4

    def to_binary(self, segmentData):
        command = bytearray([GeoNodeEnum.SET_Z_BUF, 0x01 if self.enable else 0x00, 0x00, 0x00])
        return command

    def to_c(self):
        return "GEO_ZBUFFER(" + ("1" if self.enable else "0") + "),"


class CameraNode(GeoNode):
    def __init__(self, camType, position, lookAt):
        self.camType = camType
        blender_to_sm64_scale = bpy.context.scene.fast64.sm64.blender_to_sm64_scale
        self.position = [int(round(value * blender_to_sm64_scale)) for value in position]
        self.lookAt = [int(round(value * blender_to_sm64_scale)) for value in lookAt]
        self.function = "80287D30"

        self.name = "Camera"

    def size(self):
        return 20

    def to_binary(self, segmentData):
        command = bytearray([GeoNodeEnum.CAMERA, 0x00])
        command.extend(self.camType.to_bytes(2, "big", signed=True))
        command.extend(self.position[0].to_bytes(2, "big", signed=True))
        command.extend(self.position[1].to_bytes(2, "big", signed=True))
        command.extend(self.position[2].to_bytes(2, "big", signed=True))
        command.extend(self.lookAt[0].to_bytes(2, "big", signed=True))
        command.extend(self.lookAt[1].to_bytes(2, "big", signed=True))
        command.extend(self.lookAt[2].to_bytes(2, "big", signed=True))
        append_function_address(command, self.function)
        return command

    def to_c(self):
        args = [
            str(self.camType),
            str(self.position[0]),
            str(self.position[1]),
            str(self.position[2]),
            str(self.lookAt[0]),
            str(self.lookAt[1]),
            str(self.lookAt[2]),
            address_to_decomp_function(self.function),
        ]
        return f"GEO_CAMERA({join_c_args(args)}),"


class RenderObjNode(GeoNode):
    def __init__(self):
        self.name = "Render Object"

    def size(self):
        return 4

    def to_binary(self, segmentData):
        command = bytearray([GeoNodeEnum.SETUP_OBJ_RENDER, 0x00, 0x00, 0x00])
        return command

    def to_c(self):
        return "GEO_RENDER_OBJ(),"


class BackgroundNode(GeoNode):
    def __init__(self, isColor, backgroundValue):
        self.isColor = isColor
        self.backgroundValue = backgroundValue
        self.function = "802763D4"

        self.name = "Background"

    def size(self):
        return 8

    def to_binary(self, segmentData):
        command = bytearray([GeoNodeEnum.SET_BG, 0x00])
        command.extend(self.backgroundValue.to_bytes(2, "big", signed=False))
        if self.isColor:
            command.extend(bytes.fromhex("00000000"))
        else:
            append_function_address(command, self.function)
        return command

    def to_c(self):
        if self.isColor:
            background_value_hex = format(self.backgroundValue, "04x").upper()
            return f"GEO_BACKGROUND_COLOR(0x{background_value_hex}),"
        else:
            args = [
                str(self.backgroundValue),
                address_to_decomp_function(self.function),
            ]
            return f"GEO_BACKGROUND({join_c_args(args)}),"


class CustomNode(BaseDisplayListNode):
    def __init__(
        self, command: str, arguments: str, animatable: bool, drawLayer: int, translate, rotate, add_dl: bool, dlRef: str = None
    ):
        self.command = command
        self.arguments = arguments
        self.drawLayer = drawLayer
        self.add_dl = add_dl
        self.has_dl = add_dl
        self.animatable = animatable
        self.translate = translate
        self.rotate = rotate
        self.fMesh = None
        self.DLmicrocode = None
        self.dlRef = dlRef
        # exists to get the override DL from an fMesh
        self.override_hash = None

        self.name = "Custom"

    def size(self):
        return 16

    def get_ptr_offsets(self):
        return []

    def to_binary(self, segmentData) -> bytearray:
        command = bytearray([int(self.command, 16)])
        if self.add_dl:
            command.append(int(self.drawLayer))
        if self.arguments:
            command.append(int(self.arguments, 16))
        while len(command) < 4:
            command.append(0)

        if self.translate:
            writeVectorToShorts(command, 2, self.translate)
        if self.rotate:
            for r in self.rotate.to_euler("XYZ"):
                command.extend(radian_to_sm64_degree(r, True).to_bytes(2, "big", signed=True))
        if self.add_dl:
            start_address = self.get_dl_address()
            if start_address is not None and segmentData is not None:
                command.extend(encodeSegmentedAddr(start_address, segmentData))
            else:
                command.extend(bytearray([0x00] * 4))

        return command

    def to_c(self):
        args = []
        if self.translate:
            args.extend([str(convertFloatToShort(x)) for x in self.translate])
            args[0] = f"/*trans*/ {args[0]}"
        if self.rotate:
            args.extend([str(radian_to_sm64_degree(r, True)) for r in self.rotate.to_euler("XYZ")])
            args[-3] = f"/*rot*/ {args[-3]}"
        if self.add_dl:
            args.append(f"/*dl*/ {self.get_dl_name()}")
            args = [f"/*layer*/ {get_draw_layer_enum(self.drawLayer)}"] + args

        if self.arguments:
            args.append(f"/*user input*/ {self.arguments}")
        return f"{self.command}({join_c_args(args)}),"


nodeGroupClasses = [
    StartNode,
    SwitchNode,
    TranslateRotateNode,
    TranslateNode,
    RotateNode,
    DisplayListWithOffsetNode,
    BillboardNode,
    ShadowNode,
    ScaleNode,
    StartRenderAreaNode,
    ScreenAreaNode,
    OrthoNode,
    FrustumNode,
    ZBufferNode,
    CameraNode,
    RenderRangeNode,
    CustomNode,
]

DLNodes = [
    JumpNode,
    TranslateRotateNode,
    TranslateNode,
    RotateNode,
    ScaleNode,
    DisplayListNode,
    DisplayListWithOffsetNode,
    CustomNode,
]
