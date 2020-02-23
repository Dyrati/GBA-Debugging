# ARM Debugger
An easy to use, powerful debugger.  Import a rom, and an sgm file, and set breakpoints, watchpoints, and readpoints, view/modify registers and memory, output results to a txt file, disassemble the code, and more!


## Set Up
Make sure you have Python installed, and download the repository.  You can then unpack it and open "Debugger.py", and that's it!
From there, you can type in help or ? to get detailed info on the available commands.
You can also start Debugger.py from the command line with two optional arguments: `[filepath to rom] [filepath to savestate]`

To execute CPU instructions, you'll need to import a rom.  You can use the command `importrom [filepath]`.  You can upload savestate files in .sgm format using `importstate [filepath]`.  At any time, you may create a local save only available to the current session, using `save (identifier)` (identifier is PRIORSTATE by default), which can be loaded using `load (identifier)`.

That's pretty much all you need to get started.  The rest of this readme is just here to explain some features.


## Basic Commands
- `n (count)` - execute *count* instruction(s), displaying the registers.  Count=1 by default.
- `c (count)` - execute *count* instruction(s). Count=infinity by default.
- `b [addr]` - set a breakpoint at *addr*.  CPU execution will halt after *addr* is executed.
    - if *addr* is "all", displays all break/write/readpoints
- `bw [addr]` - set a watchpoint.  CPU execution will halt after *addr* has been written to.
- `br [addr]` - set a readpoint.  CPU execution will halt after *addr* has been read from.
- `bc [condition]` - set a conditional breakpoint.  CPU execution will halt if *condition* is true.
- `d [addr]` - delete a breakpoint
    - if *addr* is "all", deletes all break/write/readpoints
- `dw [addr]` - delete a watchpoint
- `dr [addr]` - delete a readpoint
- `dc [index]` - delete a conditional breakpoint by index number
- `i` - print the CPU registers
- `dist [addr] (*count*)` - display *count* THUMB instructions starting from *addr*
- `disa [addr] (*count*)` - display *count* ARM instructions starting from *addr*
- `m [addr] (count) (size)` - display *count* units of *size* bytes of memory at *addr* (count=1, size=4 by default)

Enter in nothing to execute the previous command.  

Arguments are separated by spaces.  Arguments in brackets `[...]` are required, and parentheses `(...)` are optional.  
All commands accept [*expressions*](#expressions) as arguments, however if the command accepts multiple arguments, the expressions must not contain spaces.


## Expressions
With this debugger, you can utilize and modify registers and memory directly as though they were python variables.
You can assign values to variables by typing in: *name* = *expression*
```
test = 12345678   # creates a user variable named 'test'
```
Assigning a value to registers and memory is just as easy
```
r0 = test   # sets the actual register r0 equal to test
m($02000000) = r0   # sets the memory at $02000000 equal to r0
```
Default variables are **r0-r16, sp, lr, pc,** and **m(*addr*, *size*)**.  (size=4 by default).  r16 is CPSR  
There are also 6 global variables that may be accessed, but not directly modified:
- `MODE` - 0 if in ARM mode, 1 if in THUMB mode 
- `SIZE` - The number of bytes of the next instruction  
- `PCNT` - What the program counter will be while executing the next instruction (r15 + SIZE)  
- `ADDR` - The current address
- `INSTR` - The next instruction (in hex) to be executed
- `INSTRCOUNT` - The total number of CPU instructions executed since the beginning of the session

Attempts to modify these variables will instead create a User Variable with the same name.  
In [Execution Mode](#alternate-debugger-modes), these and any other global variables may be modified.


You can also modify variables with compound assignment operators. (+=, -=, \*=, etc).  `m(r1) += r2`  
Expressions may include any combination of variables and mathematical operations.  
Expressions may be typed directly into to the console to print their value.  
Hexadecimal numbers must be preceded by "0x", "$", or "x". 
```
base = $08000000
m(base + 0xc, 8) = 4*r0 + r1*r2 - m(r3)//4
```
**You can use expressions in place of any arguments**

If the command takes multiple arguments, then each expression must not contain spaces.
```
> chardata = $02000520
> m chardata+$14C*4 10
02000A50:  696C6546 00000078 00000000 05000000   Felix...........
02000A60:  00220046 3ACF4000 000C0020 0102001A   F."..@.: .......
02000A70:  00000000 0077006D                     ....m.w.
```


## Higher Level Commands
- `if [condition]: [command]` - execute *command* if *condition* is true
- `while [condition]: [command]` - repeat *command* while *condition* is true
- `rep/repeat [count]: [command]` - repeat *command* *count* times
- `[name][op][expression]` - create/modify a User Variable
- `def [name]: [commands]`
    - bind a list of commands separated by semicolons to *name*
    - execute these functions later by typing in "*name*()"
    - you can call functions within functions, with unlimited nesting
- `save (name)` - create a local save; *name* = PRIORSTATE by default
- `load (name)` - load a local save; *name* = PRIORSTATE by default
- `dv [name]` - delete user variable
- `df [name]` - delete user function
- `ds (name)` - delete local save; *name* = PRIORSTATE by default
- `vars` - print all user variables
- `funcs` - print all user functions
- `saves` - print all local saves  

**You can can write multiple commands in a single line by separating them with semicolons**  
if, while, and repeat only apply to one command, however that command may be anything, including a function or a loop.


## File Commands
- `importrom [filepath]` - import a rom into the debugger
- `importstate [filepath]` - import a savestate
- `exportstate (filepath)`
    - save the current state to a file; *filepath* = (most recent import) by default
    - will overwrite the destination, back up your saves!
- `reset` - reset the emulator (clears the RAM and resets the registers)
- `output [condition]`
    - after each CPU instruction, if *condition* is True, the debugger will write data to "output.txt"
    - the data outputted may be customized using the format command
    - if *condition* is "clear", deletes all of the data in "output.txt"
- `format [formatstr]` - set the format of data sent to the output file
    - *formatstr* may be a string literal; data may be interpolated using curly braces
    ```
    > output True
    > format example text {addr}: {instr}  {asm}\n  {r0-r3}
    > c 3
    ```
    Result in output.txt:
    ```
    example text 08000000: EA000108  b $08000428
      R00: 08000000  R01: 000000EA  R02: 00000000  R03: 00000000
    example text 08000428: E3A00012  mov r0, 0x12
      R00: 00000012  R01: 000000EA  R02: 00000000  R03: 00000000
    example text 0800042C: E129F000  msr cpsr_fc, r0
      R00: 00000012  R01: 000000EA  R02: 00000000  R03: 00000000
    ```
    - {addr}, {instr}, {asm}, {r0-r16}, and {cpsr} have preset formats that you can utilize in these format strings
    - you can also interpolate user variables and expressions, which may be formatted in accordance with the  
      [Python Format Specification Mini-Language](https://docs.python.org/3/library/string.html#formatspec)
    - since the length of {asm} varies, I added an option to set its length: `{asm:length}`
    - You may also use any of the following presets (default is "line"):
        - `line` = `{addr}: {instr}  {asm:20}  {cpsr}  {r0-r15}`
        - `block` = `{addr}: {instr}  {asm}\n  {r0-r3}\n  {r4-r7}\n  {r8-r11}\n  {r12-r15}\n  {cpsr}`
        - `linexl` = `{addr}:\t{instr}\t{asm:20}\t{cpsr}\t{r0-r15}`
        - `blockxl` = `{addr}:\t{instr}\t{asm:20}\t\t{cpsr}\n  {r0-r3}\n  {r4-r7}\n  {r8-r11}\n  {r12-r15}\n  {cpsr}`
```
> output true
> format line
> c 5
```
Result in output.txt:
```
08000000: EA000108  b $8000428            CPSR: [-ZC--]  R00: 08000000  R01: 000000ea  R02: 00000000  R03: 00000000  R04: 00000000  R05: 00000000  R06: 00000000  R07: 00000000  R08: 00000000  R09: 00000000  R10: 00000000  R11: 00000000  R12: 00000000  R13: 03007f00  R14: 00000000  R15: 0800042c
08000428: E3A00012  mov r0, 0x12          CPSR: [-ZC--]  R00: 00000012  R01: 000000ea  R02: 00000000  R03: 00000000  R04: 00000000  R05: 00000000  R06: 00000000  R07: 00000000  R08: 00000000  R09: 00000000  R10: 00000000  R11: 00000000  R12: 00000000  R13: 03007f00  R14: 00000000  R15: 08000430
0800042C: E129F000  msr cpsr_fc, r0       CPSR: [-----]  R00: 00000012  R01: 000000ea  R02: 00000000  R03: 00000000  R04: 00000000  R05: 00000000  R06: 00000000  R07: 00000000  R08: 00000000  R09: 00000000  R10: 00000000  R11: 00000000  R12: 00000000  R13: 03007f00  R14: 00000000  R15: 08000434
08000430: E59FD028  ldr sp, [pc, 0x28]    CPSR: [-----]  R00: 00000012  R01: 000000ea  R02: 00000000  R03: 00000000  R04: 00000000  R05: 00000000  R06: 00000000  R07: 00000000  R08: 00000000  R09: 00000000  R10: 00000000  R11: 00000000  R12: 00000000  R13: 03007fa0  R14: 00000000  R15: 08000438
08000434: E3A0001F  mov r0, 0x1f          CPSR: [-----]  R00: 0000001f  R01: 000000ea  R02: 00000000  R03: 00000000  R04: 00000000  R05: 00000000  R06: 00000000  R07: 00000000  R08: 00000000  R09: 00000000  R10: 00000000  R11: 00000000  R12: 00000000  R13: 03007fa0  R14: 00000000  R15: 0800043c
```

## Alternate Debugger Modes
In addition to Normal Mode, there is Assembly Mode and Execution Mode. 
These Modes are indicated by the input prompt.

### Assembly Mode
To enter Assembly Mode, type: `@` or `asm`.  
In this mode, you can type in Thumb Code, which is then immediately executed.  If the Thumb code is not recognized, it will attempt to execute the command in Normal Mode.  You do not need to already be in Thumb mode to execute the instruction.  
```
# display the registers

> i
R00: 00002553 R01: 030011BC R02: 6C3B3D69 R03: 00003039
R04: 080AD361 R05: 00002553 R06: 1E503FFC R07: 00000023
R08: 1E220000 R09: 080EE354 R10: 02030194 R11: 02030000
R12: 080C9F63 R13: 03007E2C R14: 080CA095 R15: 0801487C
CPSR: [----T] 0000003F
0801487A: 4B07      ldr r3, [$08014898] (=$41C64E6D)
```
```
# switch to Assembly Mode and branch to $08014878

> @
@ b $08014878
0801487A: E7FE      b $08014878
R00: 00002553 R01: 030011BC R02: 6C3B3D69 R03: 00003039
R04: 080AD361 R05: 00002553 R06: 1E503FFC R07: 00000023
R08: 1E220000 R09: 080EE354 R10: 02030194 R11: 02030000
R12: 080C9F63 R13: 03007E2C R14: 080CA095 R15: 0801487A
CPSR: [----T] 0000003F
```

### Execution Mode
To enter Execution Mode, type: `$` or `exec`.  
In this mode, you can type in real Python code, which is executed immediately.  
Here you have unrestrained access to all the global functions and variables of the script.


**To reenter Normal Mode, type: `>` or `debug`.**
