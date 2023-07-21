from dataclasses import dataclass
import json

from .find import Mio0Ptr, find_asm_pointers, findMIO0, findPointers, readU32BigEndian
from ....utility import PluginError

outStartAddress = 0x00800000
mio0HeaderLength = 0x10
compressedLength = 2

@dataclass
class mio0Header:
    destSize: int
    compOffset: int
    uncompOffset: int
    
def mio0DecodeHeader(inputBytes: bytearray):
    if inputBytes[:4] != b'MIO0':
        raise PluginError(f"Invalid bytes. Expected \"MIO0\" but first four bytes are {inputBytes[:4]}")

    return mio0Header(readU32BigEndian(inputBytes[4:8]), readU32BigEndian(inputBytes[8:12]), readU32BigEndian(inputBytes[12:16]))

def getBit(inputBytes: bytearray, bit: int):
    return (inputBytes[bit // 8] & (1 << (7 - (bit % 8))))

def mio0Decode(inputBytes: bytearray):
    head = mio0DecodeHeader(inputBytes)

    outBytes = []
    bitIndex = 0
    compIndex = 0
    uncompIndex = 0

    while len(outBytes) < head.destSize:
        break
        if getBit(inputBytes[mio0HeaderLength:], bitIndex):
            outBytes.append(inputBytes[head.uncompOffset + uncompIndex])
            uncompIndex += 1
        else:
            vals = inputBytes[head.compOffset + compIndex:]
            compIndex += 2
            length = ((vals[0] & 0xF0) >> 4) + 3
            index = ((vals[0] & 0x0F) << 8) + vals[1] + 1
            
            for i in range(length):
                outBytes.append(outBytes[len(outBytes) - index])
                
        bitIndex += 1

    return outBytes, (head.uncompOffset + uncompIndex)


def sm64_decompress_mio0(expansionProps, inputROMData: bytearray, outROMData: bytearray):
    # mio0_header_t head;
    # int bit_length;
    # int move_offset;
    # unsigned int out_addr = OUT_START_ADDR;
    alignmentAdd: int = expansionProps.MIO0Alignment - 1
    alignmentMask: int = ~alignmentAdd

    # find MIO0 locations and pointers
    mio0Table: list[Mio0Ptr] = findMIO0(inputROMData)

    findPointers(inputROMData, mio0Table)
    find_asm_pointers(inputROMData, mio0Table)

    outAddress = outStartAddress
    asDict = [ptr.__dict__ for ptr in mio0Table]
    print(json.dumps(asDict))
    return
    # extract each MIO0 block and prepend fake MIO0 header for 0x1A command and ASM references
    for mio0Ptr in mio0Table:
        oldAddress = mio0Ptr.old
#        unsigned int end;
#        int length;
#        int is_mio0 = 0;

        # align output address
        outAddress = (outAddress + alignmentAdd) & alignmentMask
        outBytes, end = mio0Decode(inputROMData[oldAddress:])
        continue
#       if (length > 0) {
#           #  dump MIO0 data and decompressed data to file
#           if (config->dump) {
#           char filename[FILENAME_MAX];
#           sprintf(filename, MIO0_DIR "/%08X.mio", in_addr);
#           write_file(filename, &in_buf[in_addr], end);
#           sprintf(filename, MIO0_DIR "/%08X", in_addr);
#           write_file(filename, &out_buf[outAddress], length);
#           }
#           #  0x1A commands and ASM references need fake MIO0 header
#           #  relocate data and add MIO0 header with all uncompressed data
#           if (ptr_table[i].command == 0x1A || ptr_table[i].command == 0xFF) {
#           bit_length = (length + 7) / 8 + 2;
#           move_offset = MIO0_HEADER_LENGTH + bit_length + COMPRESSED_LENGTH;
#           memmove(&out_buf[outAddress + move_offset], &out_buf[outAddress], length);
#           head.dest_size = length;
#           head.comp_offset = move_offset - COMPRESSED_LENGTH;
#           head.uncomp_offset = move_offset;
#           mio0_encode_header(&out_buf[outAddress], &head);
#           memset(&out_buf[outAddress + MIO0_HEADER_LENGTH], 0xFF, head.comp_offset - MIO0_HEADER_LENGTH);
#           memset(&out_buf[outAddress + head.comp_offset], 0x0, 2);
#           length += head.uncomp_offset;
#           is_mio0 = 1;
#           } else if (ptr_table[i].command == 0x18) {
#           #  0x18 commands become 0x17
#           ptr_table[i].command = 0x17;
#           }
#           #  use output from decoder to find end of ASM referenced MIO0 blocks
#           if (ptr_table[i].old_end == 0x00) {
#           ptr_table[i].old_end = in_addr + end;
#           }
#           INFO("MIO0 file %08X-%08X decompressed to %08X-%08X as raw data%s\n",
#               in_addr, ptr_table[i].old_end, outAddress, outAddress + length,
#               is_mio0 ? " with a MIO0 header" : "");
#           if (config->fill) {
#           INFO("Filling old MIO0 with 0x01 from %X length %X\n", in_addr, end);
#           memset(&out_buf[in_addr], 0x01, end);
#           }
#           #  keep track of new pointers
#           ptr_table[i].new = outAddress;
#           ptr_table[i].new_end = outAddress + length;
#           outAddress += length + config->padding;
#       } else {
#           ERROR("Error decoding MIO0 block at %X\n", in_addr);
#       }
#    }
# }
#
# INFO("Ending offset: %X\n", outAddress);
#
##  adjust pointers and ASM pointers to new values
# sm64_adjust_pointers(out_buf, in_length, ptr_table, ptr_count);
# sm64_adjust_asm(out_buf, ptr_table, ptr_count);
#
