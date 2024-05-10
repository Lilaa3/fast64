from dataclasses import dataclass
from io import BytesIO

import bpy

from ...utility import (
    PluginError,
    CData,
    toAlnum,
    get64bitAlignedAddr,
    writeIfNotFound,
    deleteIfFound,
    duplicateHierarchy,
    cleanupDuplicatedObjects,
    writeInsertableFile,
    getExportDir,
)
from ..sm64_constants import insertableBinaryTypes
from ..sm64_objects import SM64_Area, start_process_sm64_objects

from .constants import CollisionTypeDefinition


@dataclass
class CollisionVertex:
    position: tuple[int, int, int]

    def __post_init__(self):
        if len(self.position) != 3:
            raise PluginError("Vertex position should not be " + str(len(self.position) + " fields long."))

    def to_binary(self):
        data = bytearray(0)
        for field in self.position:
            data.extend(int(round(field)).to_bytes(2, "big", signed=True))
        return data

    def to_c(self):
        return f"\
COL_VERTEX({str(round(self.position[0]))}, {str(round(self.position[1]))}, {str(round(self.position[2]))}),\n"


@dataclass
class CollisionTriangle:
    indices: tuple[int, int, int]
    special_param: int | None

    def __post_init__(self):
        if len(self.indices) != 3:
            raise PluginError("Triangle indices should not be " + str(len(self.indices) + " fields long."))

    def to_binary(self):
        data = bytearray(0)
        for index in self.indices:
            data.extend(int(round(index)).to_bytes(2, "big", signed=False))
        if self.special_param is not None:
            data.extend(int(self.special_param, 16).to_bytes(2, "big", signed=False))
        return data

    def to_c(self):
        if self.special_param is None:
            return (
                "COL_TRI("
                + str(int(round(self.indices[0])))
                + ", "
                + str(int(round(self.indices[1])))
                + ", "
                + str(int(round(self.indices[2])))
                + "),\n"
            )
        return (
            "COL_TRI_SPECIAL("
            + str(int(round(self.indices[0])))
            + ", "
            + str(int(round(self.indices[1])))
            + ", "
            + str(int(round(self.indices[2])))
            + ", "
            + str(self.special_param)
            + "),\n"
        )


class Collision:
    def __init__(self, name):
        self.name = name
        self.startAddress = 0
        self.vertices = []
        # dict of collision type : triangle list
        self.triangles = {}
        self.specials = []
        self.water_boxes = []

    def set_addr(self, startAddress):
        startAddress = get64bitAlignedAddr(startAddress)
        self.startAddress = startAddress
        print("Collision " + self.name + ": " + str(startAddress) + ", " + str(self.size()))
        return startAddress, startAddress + self.size()

    def save_binary(self, romfile):
        romfile.seek(self.startAddress)
        romfile.write(self.to_binary())

    def size(self):
        return len(self.to_binary())

    def to_c(self):
        data = CData()
        data.header = "extern const Collision " + self.name + "[];\n"
        data.source = "const Collision " + self.name + "[] = {\n"
        data.source += "\tCOL_INIT(),\n"
        data.source += "\tCOL_VERTEX_INIT(" + str(len(self.vertices)) + "),\n"
        for vertex in self.vertices:
            data.source += "\t" + vertex.to_c()
        for collisionType, triangles in self.triangles.items():
            data.source += "\tCOL_TRI_INIT(" + collisionType + ", " + str(len(triangles)) + "),\n"
            for triangle in triangles:
                data.source += "\t" + triangle.to_c()
        data.source += "\tCOL_TRI_STOP(),\n"
        if len(self.specials) > 0:
            data.source += "\tCOL_SPECIAL_INIT(" + str(len(self.specials)) + "),\n"
            for special in self.specials:
                data.source += "\t" + special.to_c()
        if len(self.water_boxes) > 0:
            data.source += "\tCOL_WATER_BOX_INIT(" + str(len(self.water_boxes)) + "),\n"
            for waterBox in self.water_boxes:
                data.source += "\t" + waterBox.to_c()
        data.source += "\tCOL_END()\n" + "};\n"
        return data

    def rooms_name(self):
        return self.name + "_rooms"

    def to_c_rooms(self):
        data = CData()
        data.header = "extern const u8 " + self.rooms_name() + "[];\n"
        data.source = "const u8 " + self.rooms_name() + "[] = {\n\t"
        newlineCount = 0
        for (
            collisionType,
            triangles,
        ) in self.triangles.items():
            for triangle in triangles:
                data.source += str(triangle.room) + ", "
                newlineCount += 1
                if newlineCount >= 8:
                    newlineCount = 0
                    data.source += "\n\t"
        data.source += "\n};\n"
        return data

    def to_binary(self):
        colTypeDef = CollisionTypeDefinition()
        data = bytearray([0x00, 0x40])
        data += len(self.vertices).to_bytes(2, "big")
        for vertex in self.vertices:
            data += vertex.to_binary()
        for collisionType, triangles in self.triangles.items():
            data += getattr(colTypeDef, collisionType).to_bytes(2, "big")
            data += len(triangles).to_bytes(2, "big")
            for triangle in triangles:
                data += triangle.to_binary()
        data += bytearray([0x00, 0x41])
        if len(self.specials) > 0:
            data += bytearray([0x00, 0x43])
            data += len(self.specials).to_bytes(2, "big")
            for special in self.specials:
                data += special.to_binary()
        if len(self.water_boxes) > 0:
            data += bytearray([0x00, 0x44])
            data += len(self.water_boxes).to_bytes(2, "big")
            for waterBox in self.water_boxes:
                data += waterBox.to_binary()
        data += bytearray([0x00, 0x42])
        return data


def exportCollisionBinary(obj, transformMatrix, romfile, startAddress, endAddress, includeSpecials, includeChildren):
    collision = exportCollisionCommon(obj, transformMatrix, includeSpecials, includeChildren, obj.name, None)
    start, end = collision.set_addr(startAddress)
    if end > endAddress:
        raise PluginError("Size too big: Data ends at " + hex(end) + ", which is larger than the specified range.")
    collision.save_binary(romfile)
    return start, end


def exportCollisionC(
    obj,
    transformMatrix,
    dirPath,
    includeSpecials,
    includeChildren,
    name,
    customExport,
    writeRoomsFile,
    headerType,
    groupName,
    levelName,
):
    dirPath, texDir = getExportDir(customExport, dirPath, headerType, levelName, "", name)

    name = toAlnum(name)
    colDirPath = os.path.join(dirPath, toAlnum(name))

    if not os.path.exists(colDirPath):
        os.mkdir(colDirPath)

    colPath = os.path.join(colDirPath, "collision.inc.c")

    fileObj = open(colPath, "w", newline="\n")
    collision = exportCollisionCommon(obj, transformMatrix, includeSpecials, includeChildren, name, None)
    collisionC = collision.to_c()
    fileObj.write(collisionC.source)
    fileObj.close()

    cDefine = collisionC.header
    if writeRoomsFile:
        roomsData = collision.to_c_rooms()
        cDefine += roomsData.header
        roomsPath = os.path.join(colDirPath, "rooms.inc.c")
        roomsFile = open(roomsPath, "w", newline="\n")
        roomsFile.write(roomsData.source)
        roomsFile.close()

    headerPath = os.path.join(colDirPath, "collision_header.h")
    cDefFile = open(headerPath, "w", newline="\n")
    cDefFile.write(cDefine)
    cDefFile.close()

    if not customExport:
        if headerType == "Actor":
            # Write to group files
            if groupName == "" or groupName is None:
                raise PluginError("Actor header type chosen but group name not provided.")

            groupPathC = os.path.join(dirPath, groupName + ".c")
            groupPathH = os.path.join(dirPath, groupName + ".h")

            writeIfNotFound(groupPathC, '\n#include "' + name + '/collision.inc.c"', "")
            if writeRoomsFile:
                writeIfNotFound(groupPathC, '\n#include "' + name + '/rooms.inc.c"', "")
            else:
                deleteIfFound(groupPathC, '\n#include "' + name + '/rooms.inc.c"')
            writeIfNotFound(groupPathH, '\n#include "' + name + '/collision_header.h"', "\n#endif")

        elif headerType == "Level":
            groupPathC = os.path.join(dirPath, "leveldata.c")
            groupPathH = os.path.join(dirPath, "header.h")

            writeIfNotFound(groupPathC, '\n#include "levels/' + levelName + "/" + name + '/collision.inc.c"', "")
            if writeRoomsFile:
                writeIfNotFound(groupPathC, '\n#include "levels/' + levelName + "/" + name + '/rooms.inc.c"', "")
            else:
                deleteIfFound(groupPathC, '\n#include "levels/' + levelName + "/" + name + '/rooms.inc.c"')
            writeIfNotFound(
                groupPathH, '\n#include "levels/' + levelName + "/" + name + '/collision_header.h"', "\n#endif"
            )

    return cDefine


def exportCollisionInsertableBinary(obj, transformMatrix, filepath, includeSpecials, includeChildren):
    collision = exportCollisionCommon(obj, transformMatrix, includeSpecials, includeChildren, obj.name, None)
    start, end = collision.set_addr(0)
    if end > 0xFFFFFF:
        raise PluginError("Size too big: Data ends at " + hex(end) + ", which is larger than the specified range.")

    bytesIO = BytesIO()
    collision.save_binary(bytesIO)
    data = bytesIO.getvalue()[start:]
    bytesIO.close()

    writeInsertableFile(filepath, insertableBinaryTypes["Collision"], [], collision.startAddress, data)

    return data


def exportCollisionCommon(obj, transformMatrix, includeSpecials, includeChildren, name, areaIndex):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)

    # dict of collisionType : faces
    collisionDict = {}
    # addCollisionTriangles(obj, collisionDict, includeChildren, transformMatrix, areaIndex)
    tempObj, allObjs = duplicateHierarchy(obj, None, True, areaIndex)
    try:
        addCollisionTriangles(tempObj, collisionDict, includeChildren, transformMatrix, areaIndex)
        cleanupDuplicatedObjects(allObjs)
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
    except Exception as e:
        cleanupDuplicatedObjects(allObjs)
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        raise Exception(str(e))

    collision = Collision(toAlnum(name) + "_collision")
    for collisionType, faces in collisionDict.items():
        collision.triangles[collisionType] = []
        for faceVerts, specialParam, room in faces:
            indices = []
            for roundedPosition in faceVerts:
                index = collisionVertIndex(roundedPosition, collision.vertices)
                if index is None:
                    collision.vertices.append(CollisionVertex(roundedPosition))
                    indices.append(len(collision.vertices) - 1)
                else:
                    indices.append(index)
            collision.triangles[collisionType].append(CollisionTriangle(indices, specialParam))
    if includeSpecials:
        area = SM64_Area(areaIndex, "", "", "", None, None, [], name, None)
        # This assumes that only levels will export with included specials,
        # And that the collision exporter never will.
        start_process_sm64_objects(obj, area, transformMatrix, True)
        collision.specials = area.specials
        collision.water_boxes = area.water_boxes

    return collision


def addCollisionTriangles(obj, collisionDict, includeChildren, transformMatrix, areaIndex):
    if isinstance(obj.data, bpy.types.Mesh) and not obj.ignore_collision:
        if len(obj.data.materials) == 0:
            raise PluginError(obj.name + " must have a material associated with it.")
        obj.data.calc_loop_triangles()
        for face in obj.data.loop_triangles:
            material = obj.material_slots[face.material_index].material
            collision_props = material.fast64.sm64.collision
            if not collision_props.hasCollision:
                continue
            colType = collision_props.vanilla.get_enum()
            specialParam = collision_props.force if collision_props.set_force else None

            (x1, y1, z1) = roundPosition(transformMatrix @ obj.data.vertices[face.vertices[0]].co)
            (x2, y2, z2) = roundPosition(transformMatrix @ obj.data.vertices[face.vertices[1]].co)
            (x3, y3, z3) = roundPosition(transformMatrix @ obj.data.vertices[face.vertices[2]].co)

            nx = (y2 - y1) * (z3 - z2) - (z2 - z1) * (y3 - y2)
            ny = (z2 - z1) * (x3 - x2) - (x2 - x1) * (z3 - z2)
            nz = (x2 - x1) * (y3 - y2) - (y2 - y1) * (x3 - x2)
            magSqr = nx * nx + ny * ny + nz * nz

            if magSqr <= 0:
                print("Ignore denormalized triangle.")
                continue

            if colType not in collisionDict:
                collisionDict[colType] = []
            collisionDict[colType].append((((x1, y1, z1), (x2, y2, z2), (x3, y3, z3)), specialParam, obj.room_num))

    if includeChildren:
        for child in obj.children:
            addCollisionTriangles(
                child, collisionDict, includeChildren, transformMatrix @ child.matrix_local, areaIndex
            )


def roundPosition(position):
    return (int(round(position[0])), int(round(position[1])), int(round(position[2])))


def collisionVertIndex(vert, vertArray):
    for i in range(len(vertArray)):
        colVert = vertArray[i]
        if colVert.position == vert:
            return i
    return None


def sm64_col_register():
    bpy.types.Object.room_num = bpy.props.IntProperty(name="Room", default=0, min=0)


def sm64_col_unregister():
    del bpy.types.Object.room_num


class CollisionSettings:
    def __init__(self):
        self.collision_type = "SURFACE_DEFAULT"
        self.collision_type_simple = "SURFACE_DEFAULT"
        self.collision_custom = "SURFACE_DEFAULT"
        self.collision_all_options = False
        self.use_collision_param = False
        self.collision_param = "0x0000"

    def load(self, material):
        self.collision_type = material.collision_type
        self.collision_type_simple = material.collision_type_simple
        self.collision_custom = material.collision_custom
        self.collision_all_options = material.collision_all_options
        self.use_collision_param = material.use_collision_param
        self.collision_param = material.collision_param

    def apply(self, material):
        material.collision_type = self.collision_type
        material.collision_type_simple = self.collision_type_simple
        material.collision_custom = self.collision_custom
        material.collision_all_options = self.collision_all_options
        material.use_collision_param = self.use_collision_param
        material.collision_param = self.collision_param
