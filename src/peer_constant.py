import struct
BUF_SIZE = 1400
CHUNK_DATA_SIZE = 512*1024
HEADER_LEN = struct.calcsize("HBBHHII")
MAX_PAYLOAD = 1024
MY_TEAM = 55