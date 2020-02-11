from bisect import bisect_right


BreakState = ""
BreakPoints = set()
WatchPoints = set()
ReadPoints = set()
Conditionals = []


def undef(*args): pass


def mem_read(addr,size=4):
    region = Memory[addr >> 24 & 0xF]
    reladdr = addr % len(region)
    value = int.from_bytes(region[reladdr:reladdr+size],"little")
    if addr in ReadPoints:
        global BreakState
        BreakState = f"ReadPoint: ${addr:0>{2*size}X} (={value:0>{2*size}X})"
    return value


def mem_readsigned(addr,size=4):
    region = Memory[addr >> 24 & 0xF]
    reladdr = addr % len(region)
    value = int.from_bytes(region[reladdr:reladdr+size],"little")
    msb = 2**(8*size-1)
    value = ((value^msb) - msb) & 0xFFFFFFFF
    if addr in ReadPoints:
        global BreakState
        BreakState = f"ReadPoint: ${addr:0>{2*size}X} (={value:0>{2*size}X})"
    return value


def mem_write(addr,data,size=4):
    region = Memory[addr >> 24 & 0xF]
    reladdr = addr % len(region)
    value = int.to_bytes(data % 2**(8*size),size,"little")
    if addr in WatchPoints:
        global BreakState
        newvalue = int.from_bytes(value,"little")
        BreakState = f"WatchPoint: {addr:0>8X} ({mem_read(addr,size):0>{2*size}X} -> {newvalue:0>{2*size}X})"
    region[reladdr:reladdr+size] = value
    if mem_read(0x040000DF,1) & 2**7: DMA()


def mem_copy(src,des,size):
    region1 = Memory[src >> 24 & 0xF]
    region2 = Memory[des >> 24 & 0xF]
    src %= len(region1)
    des %= len(region2)
    copydata = region1[src:src + size]
    if src + size > len(region1): 
        copydata += region1[:(src + size) % len(region1)]
    if des + size > len(region2):
        distance = len(region2) - des
        region2[des:] = copydata[:distance]
        region2[:size-distance] = copydata[distance:size-distance]
    else:
        region2[des:des+size] = copydata


def DMA():
    src = mem_read(0x040000D4,4)
    des = mem_read(0x040000D8,4)
    count = mem_read(0x040000DC,2)
    control = mem_read(0x040000DE,2)
    mem_copy(src, des, count*(2 + 2*(control >> 10 & 1)))
    mem_write(0x040000DE, control & 0x7FFF, 2)


def compare(Op1,Op2,S=1):
    result = (Op1 & 0xFFFFFFFF) + (Op2 & 0xFFFFFFFF)
    sign1 = Op1 >> 30
    sign2 = Op2 >> 30
    N = 8 if result & 2**31 else 0
    Z = 4 if not result & 0xFFFFFFFF else 0
    C = 2 if result & 2**32 else 0
    V = 1 if sign1 == sign2 != N else 0
    if S: Reg[16] = (N|Z|C|V) << 28 | Reg[16] & 2**28-1
    return result & 0xFFFFFFFF


def cmphalf(result,S=1):
    result &= 0xFFFFFFFF
    N = 8 if result & 2**31 else 0
    Z = 4 if not result else 0
    if S: Reg[16] = (N|Z) << 28 | Reg[16] & 2**30-1
    return result


def barrelshift(value,Shift,Typ,S=0):
    value &= 0xFFFFFFFF
    if Typ == 3: Shift &= 31
    else: Shift = min(32,Shift)
    affectedflags = 0xE << 28
    if Shift: 
        C = 2*min(1, value & 1 << Shift-1)
        if Typ == 0: value <<= Shift; C = value >> 32 & 1
        elif Typ == 1: value >>= Shift
        elif Typ == 2: value = (value ^ 2**31) - 2**31 >> Shift
        elif Typ == 3: value = (value << 32 | value) >> Shift
    else:
        C = 2*(value>>31)
        if Typ == 0: affectedflags = 0xC << 28; C = 0
        elif Typ == 1: value = 0
        elif Typ == 2: value = -(value>>31)
        elif Typ == 3: value = ((Reg[16] & 1<<29) << 3 | value) >> 1
    value &= 0xFFFFFFFF
    N = 8 if value & 2**31 else 0
    Z = 4 if not value else 0
    if S: Reg[16] = Reg[16] & ~affectedflags | (N|Z|C) << 28
    return value


conditions = (
    lambda cpsr: cpsr & 4 == 4,             # EQ: Z=1
    lambda cpsr: cpsr & 4 == 0,             # NE: Z=0
    lambda cpsr: cpsr & 2 == 2,             # CS/HS: C=1
    lambda cpsr: cpsr & 2 == 0,             # CC/LO: C=0
    lambda cpsr: cpsr & 8 == 8,             # MI: N=1
    lambda cpsr: cpsr & 8 == 0,             # PL: N=0
    lambda cpsr: cpsr & 1 == 1,             # VS: V=1
    lambda cpsr: cpsr & 1 == 0,             # VC: V=0
    lambda cpsr: cpsr & 6 == 2,             # HI: C=1 and Z=0
    lambda cpsr: cpsr & 6 != 2,             # LS: C=0 or Z=1
    lambda cpsr: cpsr & 9 in {0,9},         # GE: N=V
    lambda cpsr: cpsr & 9 not in {0,9},     # LT: N!=V
    lambda cpsr: cpsr & 13 in {0,9},        # GT: Z=0 and N=V
    lambda cpsr: cpsr & 13 in {5,12},       # LE: Z=1 and N!=V
    lambda cpsr: True,                      # AL: Always true
    lambda cpsr: False,                     # NV: Never true
)


#######################
### THUMB FUNCTIONS ###
#######################


def shifted(instr):
    Op,Offset,Rs,Rd = instr>>11 & 3, instr>>6 & 31, instr>>3 & 7, instr & 7
    Reg[Rd] = barrelshift(Reg[Rs],Offset,Op,1)


def addsub(instr):
    I,Op,Rn,Rs,Rd = instr>>10 & 1, instr>>9 & 1, instr>>6 & 7, instr>>3 & 7, instr & 7
    Rs = Reg[Rs]
    if not I: Rn = Reg[Rn]
    if not Op: Reg[Rd] = compare(Rs,Rn)
    else: Reg[Rd] = compare(Rs,-Rn)
    

def immediate(instr):
    Op,Rd,Offset = instr>>11 & 3, instr>>8 & 7, instr & 0xFF
    Op1 = Reg[Rd]
    if Op == 0: Reg[Rd] = cmphalf(Offset)
    elif Op == 1: compare(Reg[Rd], -Offset)
    elif Op == 2: Reg[Rd] = compare(Reg[Rd], Offset)
    elif Op == 3: Reg[Rd] = compare(Reg[Rd],-Offset)


alu_ops = (
    lambda Rd,Rs: cmphalf(Rd & Rs),                        # AND
    lambda Rd,Rs: cmphalf(Rd ^ Rs),                        # XOR
    lambda Rd,Rs: barrelshift(Rd,Rs & 0x1F,0,1),           # LSL
    lambda Rd,Rs: barrelshift(Rd,Rs & 0x1F,1,1),           # LSR
    lambda Rd,Rs: barrelshift(Rd,Rs & 0x1F,2,1),           # ASR
    lambda Rd,Rs: compare(Rd, Rs + (Reg[16]>>29 & 1)),     # ADC
    lambda Rd,Rs: compare(Rd,-Rs + (Reg[16]>>29 & 1) - 1), # SBC
    lambda Rd,Rs: barrelshift(Rd,Rs & 0x1F,3,1),           # ROR
    lambda Rd,Rs: cmphalf(Rd & Rs),                        # TST
    lambda Rd,Rs: compare(0,-Rs),                          # NEG
    lambda Rd,Rs: compare(Rd,-Rs),                         # CMP
    lambda Rd,Rs: compare(Rd, Rs),                         # CMN
    lambda Rd,Rs: cmphalf(Rd | Rs),                        # ORR
    lambda Rd,Rs: cmphalf(Rd * Rs),                        # MUL
    lambda Rd,Rs: cmphalf(Rd & ~Rs),                       # BIC
    lambda Rd,Rs: cmphalf(~Rs),                            # MVN
)

def AluOp(instr):
    Op,Rs,Rd = instr>>6 & 15, instr>>3 & 7, instr & 7
    result = alu_ops[Op](Reg[Rd],Reg[Rs])
    if Op not in {8,10,11}: Reg[Rd] = result


def HiRegBx(instr):
    Op,Hd,Hs,Rs,Rd = instr>>8 & 3, instr>>7 & 1, instr>>6 & 1, instr>>3 & 7, instr & 7
    Rd += 8*Hd
    Rs += 8*Hs
    if Op == 0: Reg[Rd] += Reg[Rs]
    elif Op == 1: compare(Reg[Rd],-Reg[Rs])
    elif Op == 2: Reg[Rd] = Reg[Rs]
    elif Op == 3:
        Mode = Reg[Rs] & 1
        if Hd: Reg[14] = Reg[15] + 1
        Reg[15] = Reg[Rs] + 4-3*Mode
        Reg[16] = Reg[16] & ~(1<<5) | Mode << 5


def ldr_pc(instr):
    Rd,Word = instr>>8 & 7, instr & 0xFF
    Reg[Rd] = mem_read(Reg[15] + Word*4 - (Reg[15] & 2), 4)


def ldrstr(instr):
    Op,S,Ro,Rb,Rd = instr>>10 & 3, instr>>9 & 1, instr>>6 & 7, instr>>3 & 7, instr & 7
    addr = Reg[Rb] + Reg[Ro]
    if not S:
        if Op == 0: mem_write(addr, Reg[Rd], 4)
        elif Op == 1: mem_write(addr, Reg[Rd], 1)
        elif Op == 2: Reg[Rd] = mem_read(addr, 4)
        elif Op == 3: Reg[Rd] = mem_read(addr, 1)
    else:
        if Op == 0: mem_write(addr, Reg[Rd], 2)
        elif Op == 1: Reg[Rd] = mem_readsigned(addr, 1)
        elif Op == 2: Reg[Rd] = mem_read(addr, 2)
        elif Op == 3: Reg[Rd] = mem_readsigned(addr, 2)


def ldrstr_imm(instr):
    Op,L,Offset,Rb,Rd = instr>>12 & 3, instr>>11 & 1, instr>>6 & 31, instr>>3 & 7, instr & 7
    size = Op^2 if Op != 2 else 4  # (3,2,0) -> (1,4,2)
    addr = Reg[Rb] + Offset*size
    if not L: mem_write(addr, Reg[Rd], size)
    else: Reg[Rd] = mem_read(addr, size)


def ldrstr_sp(instr):
    Op,Rd,Word = instr>>11 & 1, instr>>8 & 7, instr & 0xFF
    if not Op: mem_write(Reg[13] + Word*4, Reg[Rd], 4)
    else: Reg[Rd] = mem_read(Reg[13] + Word*4, 4)


def get_reladdr(instr):
    Op,Rd,Word = instr>>11 & 1, instr>>8 & 7, instr & 0xFF
    if not Op: Reg[Rd] = Reg[15] - (Reg[15] & 2) + Word*4
    else: Reg[Rd] = Reg[13] + Word*4


def add_sp(instr):
    S,Word = instr>>7 & 1, instr & 0x7F
    if not S: Reg[13] += Word*4
    else: Reg[13] -= Word*4


def pushpop(instr):
    Op,Rlist = instr>>11 & 1, instr & 0x1FF
    Rlist = [i for i in range(9) if Rlist & 2**i]
    if Rlist[-1] == 8: Rlist[-1] = 14 + Op
    if not Op:
        for i in reversed(Rlist):
            Reg[13] -= 4
            mem_write(Reg[13], Reg[i], 4)
    else:
        for i in Rlist:
            Reg[i] = mem_read(Reg[13], 4)
            Reg[13] += 4
        if Reg[15] & 1: Reg[15] += 1


def stmldm(instr):
    Op,Rb,Rlist = instr>>11 & 1, instr>>8 & 7, instr & 0xFF
    addr = Reg[Rb]
    for i in range(8):
        if Rlist & 2**i:
            if not Op: mem_write(addr, Reg[i], 4)
            else: Reg[i] = mem_read(addr, 4)
            addr += 4
    Reg[Rb] = addr


def b_if(instr):
    Cond,Offset = instr>>8 & 15, instr & 0xFF
    if conditions[Cond](Reg[16]>>28): Reg[15] += ((Offset^0x80) - 0x80)*2 + 2


def branch(instr):
    Reg[15] += ((instr & 0x7FF ^ 0x400) - 0x400)*2 + 2


def bl(instr):
    if instr == 0xF800:
        link = Reg[15] - 1
        Reg[15] = Reg[14] + 2
        Reg[14] = link
    else:
        Reg[14] = Reg[15] + 1
        Reg[15] += (((instr & 0x7FF ^ 0x400) << 11 | (instr >> 16) & 0x7FF) - 0x200000)*2 + 2


ThumbBounds = (
    0x1800,0x2000,0x4000,0x4400,0x4800,0x5000,0x6000,0x8000,0x9000,0xA000,
    0xB000,0xB400,0xBE00,0xC000,0xD000,0xDE00,0xDF00,0xE000,0xE800,0xF000,
)

ThumbFuncs = (
    shifted, addsub, immediate, AluOp, HiRegBx, ldr_pc, ldrstr, ldrstr_imm, ldrstr_imm, ldrstr_sp,
    get_reladdr, add_sp, pushpop, undef, stmldm, b_if, undef, undef, branch, undef, bl
)



#####################
### ARM FUNCTIONS ###
#####################


dataprocess_list = (
    lambda Rn,Op2,S: cmphalf(Rn & Op2, S),                         # AND
    lambda Rn,Op2,S: cmphalf(Rn ^ Op2, S),                         # EOR
    lambda Rn,Op2,S: compare(Rn, -Op2, S),                         # SUB
    lambda Rn,Op2,S: compare(Op2, -Rn, S),                         # RSB
    lambda Rn,Op2,S: compare(Rn, Op2, S),                          # ADD
    lambda Rn,Op2,S: compare(Rn, Op2 + (Reg[16]>>29 & 1), S),      # ADC
    lambda Rn,Op2,S: compare(Rn,-Op2 + (Reg[16]>>29 & 1) - 1, S),  # SBC
    lambda Rn,Op2,S: compare(Op2,-Rn + (Reg[16]>>29 & 1) - 1, S),  # RSC
    lambda Rn,Op2,S: cmphalf(Rn & Op2, S),                         # TST
    lambda Rn,Op2,S: cmphalf(Rn ^ Op2, S),                         # TEQ
    lambda Rn,Op2,S: compare(Rn, -Op2, S),                         # CMP
    lambda Rn,Op2,S: compare(Rn, Op2, S),                          # CMN
    lambda Rn,Op2,S: cmphalf(Rn | Op2, S),                         # ORR
    lambda Rn,Op2,S: cmphalf(Op2, S),                              # MOV
    lambda Rn,Op2,S: cmphalf(Rn & ~Op2, S),                        # BIC
    lambda Rn,Op2,S: cmphalf(~Op2, S),                             # MVN
)


def dataprocess(instr):
    i = instr
    Imm, OpCode, S, Rn, Rd, Shift, Typ, Imm2, Rm = (
        i>>25 & 1, i>>21 & 15, i>>20 & 1, i>>16 & 15, i>>12 & 15, i>>7 & 31, i>>5 & 3, i>>4 & 1, i & 15)
    if Imm:
        Op2 = i & 0xFF
        Shift = (i >> 8 & 15)*2
        Op2 = ((Op2 & 2**Shift-1) << 32 | Op2) >> Shift
    else:
        if Imm2: Shift = Reg[Shift>>1 & 15]
        Op2 = barrelshift(Reg[Rm],Shift,Typ,S)
    result = dataprocess_list[OpCode](Reg[Rn],Op2,S)
    if not(8 <= OpCode <= 11): Reg[Rd] = result


def psr(instr):
    i = instr
    I, P, L, Field, Rd, Shift, Imm, Rm = (
        i>>25 & 1, i>>22 & 1, i>>21 & 1, i>>16 & 15, i>>12 & 15, i>>8 & 15, i & 0xFF, i & 15)
    if not P:
        if L:
            bitmask = 15<<28*(Field>>3) | 0xEF*(Field & 1)
            if I: Op = barrelshift(Imm, Shift*2, 3)
            else: Op = Reg[Rm]
            Reg[16] = Reg[16] & ~bitmask | Op & bitmask
        else: R[Rd] = R[16]


def arm_bx(instr):
    L, Rn = instr >> 5 & 1, instr & 15
    if L: Reg[14] = Reg[15] - 4
    Mode = Reg[Rn] & 1
    Reg[15] = Reg[Rn] + 4-3*Mode
    Reg[16] = Reg[16] & ~(1<<5) | Mode << 5


def arm_branch(instr):
    L, Offset = instr >> 24 & 1, instr & 0xFFFFFF
    if L: Reg[14] = Reg[15] - 4
    Reg[15] += 4 + Offset*4


def clz(instr):
    Rd,Rm = instr >> 12 & 15, instr & 15    
    Reg[Rd] = 32 - int.bit_length(Reg[Rm])


def multiply(instr):
    i = instr
    OpCode, S, Rd, Rn, Rs, y, x, Rm = (i>>21 & 15, i>>20 & 1, i>>16 & 15, i>>12 & 15, i>>8 & 15, i>>6 & 1, i>>5 & 1, i & 15)
    Rm, Rs = Reg[Rm], Reg[Rs]
    if OpCode & 8:  #half registers
        OpCode &= 3
        S = 0
        Rs = (Rs >> 16*y & 0xFFFF ^ 2**15) - 2**15
        if OpCode != 1: Rm = (Rm >> 16*x & 0xFFFF ^ 2**15) - 2**15
        if OpCode == 0: Reg[Rd] = (Rm*Rs + Reg[Rn]) % 2**32
        elif OpCode == 1: 
            Rm = (Rm ^ 2**31) - 2**31
            Reg[Rd] = ((Rm*Rs >> 16) + Reg[Rn]*(1-x)) % 2**32
        elif OpCode == 2:
            result = (Reg[Rd] << 32 | Reg[Rn]) + Rm*Rs
            Reg[Rd] = result >> 32 & 0xFFFFFFFF
            Reg[Rn] = result & 0xFFFFFFFF
        elif OpCode == 3:
            Reg[Rd] = Rm*Rs
    else:
        if OpCode & 2:  #signed
            Rm = (Rm ^ 2**31) - 2**31
            Rs = (Rs ^ 2**31) - 2**31
        result = Rm*Rs + Reg[Rn]*(OpCode & 1)
        if OpCode & 4: 
            Reg[Rd] = result >> 32 & 0xFFFFFFFF
            Reg[Rn] = result & 0xFFFFFFFF
        else: 
            Reg[Rd] = result & 0xFFFFFFFF
        if S:
            N = 8 if result & 2**63 else 0
            Z = 4 if not result & 2**63-1 else 0
            Reg[16] = (N|Z)<<28 | (Reg[16] & 2**30-1)


def datatransfer(instr):
    Flags, Rn, Rd, Offset = (instr>>20 & 0x7F, instr>>16 & 15, instr>>12 & 15, instr & 0xFFF)
    #Flags: Single/Double, Immediate offset, Pre/Post index, Up/Down, Byte/Int, Writeback, Load/Store
    D,I,P,U,B,W,L = (1 if Flags & 2**(6-i) else 0 for i in range(7))
    Shift, Typ, Rm = Offset>>7 & 31, Offset>>5 & 3, Offset & 15
    U = (-1,1)[U]
    addr = Reg[Rn]
    if D:
        if I: Offset = barrelshift(Reg[Rm],Shift,Typ)
        if P: addr += Offset*U
        if not P or W: Reg[Rn] += Offset*U
        if L: Reg[Rd] = mem_read(addr, 4 - 3*B)
        else: mem_write(addr, Reg[Rd], 4 - 3*B)
    else:
        Rm = Offset & 15
        # B is Immediate offset flag when D is set
        if B: Offset = (Offset >> 8 & 15) << 4 | Offset & 15
        else: Offset = Reg[Rm]
        if P: addr += Offset*U
        if not P or W: Reg[Rn] += Offset*U
        if Typ == 0:
            temp = Reg[Rm]  # in case Rm == Rd
            Reg[Rd] = mem_read(Reg[Rn],2-B)
            mem_write(Reg[Rn],temp,2-B)
        elif L:
            if Typ == 1: Reg[Rd] = mem_read(addr,2)
            elif Typ == 2: Reg[Rd] = mem_readsigned(addr,1)
            elif Typ == 3: Reg[Rd] = mem_readsigned(addr,2)
        else:
            if Typ == 1: mem_write(addr,Reg[Rd],2)
            elif Typ == 2: Reg[Rd],Reg[Rd+1] = mem_read(addr,4), mem_read(addr + 4,4)
            elif Typ == 3: mem_write(addr,Reg[Rd],4); mem_write(addr + 4,Reg[Rd+1],4)


def blocktransfer(instr):
    Flags,Rn,Rlist = instr>>20 & 31, instr>>16 & 15, instr & 0xFFFF
    #Flags: Pre/Post, Up/Down, Load PSR, Writeback, Load/Store
    P,U,S,W,L = (1 if Flags & 2**(4-i) else 0 for i in range(5))
    direction = (-1,1)[U]
    addr = Reg[Rn]
    if P: addr += 4*direction
    index = (15,0)[U]
    for i in range(16):
        if Rlist & 1<<index:
            if L: Reg[index] = mem_read(addr,4)
            else: mem_write(addr,Reg[index],4)
            addr += 4*direction
        index += direction
    if P: addr -= 4*direction
    if W: Reg[Rn] = addr


arm_tree = {
    0:(27,36), 1:(26,31), 2:(25,28), 3:(4,9), 4:([25<<20,16<<20],6), 5:dataprocess, 6:(7,8), 7:psr, 
    8:multiply, 9:(7,19), 10:([25<<20,16<<20],12), 11:dataprocess, 12:(6,16), 13:(22,15), 14:arm_bx, 15:clz, 
    16:(5,18), 17:undef, 18:undef, 19:([3<<5,0],23), 20:(22,22), 21:datatransfer, 22:datatransfer, 23:(24,27), 
    24:(23,26), 25:multiply, 26:multiply, 27:datatransfer, 28:([25<<20,16<<20],30), 29:dataprocess, 30:psr, 31:(25,33), 
    32:datatransfer, 33:(4,35), 34:datatransfer, 35:undef, 36:(26,40), 37:(25,39), 38:blocktransfer, 39:arm_branch,
    40:(25,44), 41:([15<<21,2<<21],43), 42:undef, 43:undef, 44:(24,48), 45:(4,47), 46:undef, 47:undef,
    48:undef
}


def navigateTree(instr,tree):
    treepos = 0
    while True:
        try: 
            condition = tree[treepos][0]
            if type(condition) == int:
                if instr>>condition & 1: treepos = tree[treepos][1]
                else: treepos += 1
            else:
                bitmask,value = condition
                if instr & bitmask == value: treepos = tree[treepos][1]
                else: treepos += 1
        except TypeError:
            return tree[treepos]


def execute(instr,mode):
    global BreakState
    BreakState = ""
    # THUMB
    if mode:
        Reg[15] += 2
        ID = bisect_right(ThumbBounds,instr)
        ThumbFuncs[ID](instr)
    # ARM
    else:
        Reg[15] += 4
        Cond = instr >> 28
        if conditions[Cond](Reg[16]>>28):
            arm_function = navigateTree(instr,arm_tree)
            arm_function(instr)