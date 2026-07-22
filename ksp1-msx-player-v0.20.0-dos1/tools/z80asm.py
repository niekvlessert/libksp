#!/usr/bin/env python3
"""Small deterministic two-pass Z80 assembler used by KSP1PLAY.

It intentionally supports only the instruction/directive subset used by this
project. No external assembler is required.
"""
from __future__ import annotations
import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path

class AsmError(Exception):
    pass

@dataclass
class Line:
    path: Path
    number: int
    text: str

REG8 = {'b':0,'c':1,'d':2,'e':3,'h':4,'l':5,'(hl)':6,'a':7}
REG16 = {'bc':0,'de':1,'hl':2,'sp':3}
PUSH16 = {'bc':0,'de':1,'hl':2,'af':3}
CC = {'nz':0,'z':1,'nc':2,'c':3,'po':4,'pe':5,'p':6,'m':7}
JRCC = {'nz':0,'z':1,'nc':2,'c':3}


def split_csv(s: str) -> list[str]:
    out=[]; cur=[]; depth=0; quote=None; esc=False
    for ch in s:
        if quote:
            cur.append(ch)
            if esc: esc=False
            elif ch=='\\': esc=True
            elif ch==quote: quote=None
            continue
        if ch in "'\"": quote=ch; cur.append(ch)
        elif ch=='(': depth+=1; cur.append(ch)
        elif ch==')': depth-=1; cur.append(ch)
        elif ch==',' and depth==0:
            out.append(''.join(cur).strip()); cur=[]
        else: cur.append(ch)
    if cur or s.strip(): out.append(''.join(cur).strip())
    return out




def lower_outside_quotes(s: str) -> str:
    """Lowercase assembler syntax while preserving quoted character/string case."""
    out=[]; quote=None; esc=False
    for ch in s:
        if quote:
            out.append(ch)
            if esc:
                esc=False
            elif ch=='\\':
                esc=True
            elif ch==quote:
                quote=None
        else:
            if ch in "\'\"":
                quote=ch
                out.append(ch)
            else:
                out.append(ch.lower())
    return ''.join(out)
def strip_comment(s: str) -> str:
    quote=None; esc=False
    for i,ch in enumerate(s):
        if quote:
            if esc: esc=False
            elif ch=='\\': esc=True
            elif ch==quote: quote=None
        elif ch in "'\"": quote=ch
        elif ch==';': return s[:i]
    return s


def normalize_expr(expr: str) -> str:
    expr = expr.strip().replace('$', '__pc__')
    # Allow 1234h style if ever used.
    expr = re.sub(r'\b([0-9A-Fa-f]+)[Hh]\b', lambda m: '0x'+m.group(1), expr)
    return expr

class ExprEval(ast.NodeVisitor):
    def __init__(self, symbols, pc, allow_unknown):
        self.symbols=symbols; self.pc=pc; self.allow_unknown=allow_unknown
    def visit_Expression(self,n): return self.visit(n.body)
    def visit_Constant(self,n):
        if isinstance(n.value,(int,bool)): return int(n.value)
        if isinstance(n.value,str) and len(n.value)==1: return ord(n.value)
        raise AsmError('bad constant')
    def visit_Name(self,n):
        if n.id=='__pc__': return self.pc
        key=n.id.lower()
        if key in self.symbols: return self.symbols[key]
        if self.allow_unknown: return 0
        raise AsmError(f'unknown symbol {n.id}')
    def visit_UnaryOp(self,n):
        v=self.visit(n.operand)
        if isinstance(n.op,ast.USub): return -v
        if isinstance(n.op,ast.UAdd): return v
        if isinstance(n.op,ast.Invert): return ~v
        raise AsmError('bad unary op')
    def visit_BinOp(self,n):
        a=self.visit(n.left); b=self.visit(n.right)
        ops={ast.Add:a+b, ast.Sub:a-b, ast.Mult:a*b, ast.FloorDiv:a//b if b else 0,
             ast.Mod:a%b if b else 0, ast.LShift:a<<b, ast.RShift:a>>b,
             ast.BitOr:a|b, ast.BitAnd:a&b, ast.BitXor:a^b}
        for t,v in ops.items():
            if isinstance(n.op,t): return v
        raise AsmError('bad binary op')
    def generic_visit(self,n): raise AsmError(f'unsupported expression {type(n).__name__}')

def eval_expr(expr, symbols, pc, allow_unknown=False):
    try:
        tree=ast.parse(normalize_expr(expr), mode='eval')
        return ExprEval(symbols,pc,allow_unknown).visit(tree)
    except (SyntaxError,AsmError) as e:
        if isinstance(e,AsmError): raise
        raise AsmError(f'bad expression {expr!r}') from e

def is_indirect(op):
    op=op.strip()
    return len(op)>=2 and op[0]=='(' and op[-1]==')'

def inner(op): return op.strip()[1:-1].strip()

def lo(v): return v & 0xff

def word(v): return [v&0xff,(v>>8)&0xff]

class Assembler:
    def __init__(self):
        self.symbols={}; self.lines=[]; self.origin=None; self.pc=0; self.output=bytearray(); self.listing=[]

    def load(self, path: Path):
        path=path.resolve()
        for num,raw in enumerate(path.read_text(encoding='utf-8').splitlines(),1):
            text=strip_comment(raw).rstrip()
            if not text.strip():
                self.lines.append(Line(path,num,'')); continue
            m=re.match(r'^\s*include\s+[\'\"](.+?)[\'\"]\s*$',text,re.I)
            if m:
                inc=(path.parent/m.group(1)).resolve(); self.load(inc); continue
            self.lines.append(Line(path,num,text))

    def parse_line(self,line:Line,passno:int):
        s=line.text.strip()
        if not s: return b''
        # one or more leading labels
        while True:
            m=re.match(r'^([A-Za-z_.$][\w.$]*):\s*(.*)$',s)
            if not m: break
            name=m.group(1).lower()
            if passno==1:
                if name in self.symbols: raise AsmError(f'duplicate symbol {name}')
                self.symbols[name]=self.pc
            s=m.group(2).strip()
            if not s: return b''
        m=re.match(r'^([A-Za-z_.$][\w.$]*)\s+equ\s+(.+)$',s,re.I)
        if m:
            name=m.group(1).lower(); val=eval_expr(m.group(2),self.symbols,self.pc,passno==1)
            if passno==1: self.symbols[name]=val
            return b''
        parts=s.split(None,1); op=parts[0].lower(); args=parts[1].strip() if len(parts)>1 else ''
        if op=='org':
            val=eval_expr(args,self.symbols,self.pc,passno==1)
            if self.origin is None: self.origin=val
            self.pc=val
            return b''
        if op in ('db','defb'):
            out=bytearray()
            for item in split_csv(args):
                item=item.strip()
                if len(item)>=2 and item[0] in "'\"" and item[-1]==item[0]:
                    try: val=ast.literal_eval(item)
                    except Exception as e: raise AsmError(f'bad string {item}') from e
                    if isinstance(val,str): out.extend(val.encode('latin1'))
                    elif isinstance(val,bytes): out.extend(val)
                    else: raise AsmError('db string expected')
                else: out.append(lo(eval_expr(item,self.symbols,self.pc+len(out),passno==1)))
            return bytes(out)
        if op in ('dw','defw'):
            out=bytearray()
            for item in split_csv(args): out.extend(word(eval_expr(item,self.symbols,self.pc+len(out),passno==1)))
            return bytes(out)
        if op in ('ds','defs'):
            vals=split_csv(args); n=eval_expr(vals[0],self.symbols,self.pc,passno==1); fill=eval_expr(vals[1],self.symbols,self.pc,passno==1) if len(vals)>1 else 0
            if n<0: raise AsmError('negative ds')
            return bytes([lo(fill)])*n
        operands=[lower_outside_quotes(x.strip()) for x in split_csv(args)] if args else []
        return bytes(self.encode(op,operands,passno==1))

    def imm(self,s,unknown=False): return eval_expr(s,self.symbols,self.pc,unknown)
    def rel(self,s,length,unknown=False):
        target=self.imm(s,unknown); d=target-(self.pc+length)
        if not unknown and not -128<=d<=127: raise AsmError(f'relative target out of range ({d})')
        return d&0xff

    def encode(self,op,o,u):
        one={'nop':0x00,'rlca':0x07,'rrca':0x0f,'rla':0x17,'rra':0x1f,'daa':0x27,'cpl':0x2f,
             'scf':0x37,'ccf':0x3f,'halt':0x76,'exx':0xd9,'di':0xf3,'ei':0xfb,'ret':0xc9}
        if op in one and not o: return [one[op]]
        if op=='ld' and o==['a','i']: return [0xed,0x57]
        if op=='neg' and not o:return [0xed,0x44]
        if op=='reti' and not o:return [0xed,0x4d]
        if op=='retn' and not o:return [0xed,0x45]
        if op=='ldi' and not o:return [0xed,0xa0]
        if op=='ldir' and not o:return [0xed,0xb0]
        if op=='lddr' and not o:return [0xed,0xb8]
        if op=='cpir' and not o:return [0xed,0xb1]
        if op=='im' and len(o)==1:
            v=self.imm(o[0],u); return [0xed,{0:0x46,1:0x56,2:0x5e}[v]]
        if op=='rst' and len(o)==1:
            v=self.imm(o[0],u)
            if v%8 or not 0<=v<=56: raise AsmError('bad rst')
            return [0xc7+v]
        if op=='ret' and len(o)==1 and o[0] in CC:return [0xc0+CC[o[0]]*8]
        if op=='jp':
            if len(o)==1:
                if o[0]=='(hl)':return [0xe9]
                return [0xc3]+word(self.imm(o[0],u))
            if len(o)==2 and o[0] in CC:return [0xc2+CC[o[0]]*8]+word(self.imm(o[1],u))
        if op=='jr':
            # For this self-contained project, JR is deliberately assembled as JP.
            # This avoids fragile range failures while retaining source readability.
            if len(o)==1:return [0xc3]+word(self.imm(o[0],u))
            if len(o)==2 and o[0] in JRCC:return [0xc2+CC[o[0]]*8]+word(self.imm(o[1],u))
        if op=='djnz' and len(o)==1:return [0x10,self.rel(o[0],2,u)]
        if op=='call':
            if len(o)==1:return [0xcd]+word(self.imm(o[0],u))
            if len(o)==2 and o[0] in CC:return [0xc4+CC[o[0]]*8]+word(self.imm(o[1],u))
        if op=='push' and len(o)==1 and o[0] in PUSH16:return [0xc5+PUSH16[o[0]]*0x10]
        if op=='pop' and len(o)==1 and o[0] in PUSH16:return [0xc1+PUSH16[o[0]]*0x10]
        if op=='ex' and len(o)==2:
            if o==['de','hl']:return [0xeb]
            if o==['(sp)','hl']:return [0xe3]
            if o==['af',"af'"]:return [0x08]
        if op=='ld' and len(o)==2:
            d,s=o
            if d in REG8 and s in REG8:return [0x40+REG8[d]*8+REG8[s]]
            if d=='sp' and s=='hl':return [0xf9]
            if d in REG8 and not is_indirect(s):return [0x06+REG8[d]*8,lo(self.imm(s,u))]
            if d in REG16 and not is_indirect(s):return [0x01+REG16[d]*0x10]+word(self.imm(s,u))
            if d=='a' and s=='(bc)':return [0x0a]
            if d=='a' and s=='(de)':return [0x1a]
            if d=='(bc)' and s=='a':return [0x02]
            if d=='(de)' and s=='a':return [0x12]
            if is_indirect(d):
                x=inner(d)
                if x=='hl' and s in REG8:return [0x70+REG8[s]]
                if x=='hl':return [0x36,lo(self.imm(s,u))]
                addr=self.imm(x,u)
                if s=='a':return [0x32]+word(addr)
                if s=='hl':return [0x22]+word(addr)
                if s in ('bc','de','sp'):
                    return [0xed,{'bc':0x43,'de':0x53,'sp':0x73}[s]]+word(addr)
            if is_indirect(s):
                x=inner(s)
                if x=='hl' and d in REG8:return [0x46+REG8[d]*8]
                addr=self.imm(x,u)
                if d=='a':return [0x3a]+word(addr)
                if d=='hl':return [0x2a]+word(addr)
                if d in ('bc','de','sp'):
                    return [0xed,{'bc':0x4b,'de':0x5b,'sp':0x7b}[d]]+word(addr)
        if op in ('inc','dec') and len(o)==1:
            x=o[0]
            if x in REG8:return [(0x04 if op=='inc' else 0x05)+REG8[x]*8]
            if x in REG16:return [(0x03 if op=='inc' else 0x0b)+REG16[x]*0x10]
        if op=='add' and len(o)==2:
            if o[0]=='hl' and o[1] in REG16:return [0x09+REG16[o[1]]*0x10]
            if o[0]=='a':
                s=o[1]
                if s in REG8:return [0x80+REG8[s]]
                return [0xc6,lo(self.imm(s,u))]
        if op=='adc' and len(o)==2:
            if o[0]=='hl' and o[1] in REG16:return [0xed,0x4a+REG16[o[1]]*0x10]
            if o[0]=='a':
                s=o[1]
                if s in REG8:return [0x88+REG8[s]]
                return [0xce,lo(self.imm(s,u))]
        if op=='sbc' and len(o)==2:
            if o[0]=='hl' and o[1] in REG16:return [0xed,0x42+REG16[o[1]]*0x10]
            if o[0]=='a':
                s=o[1]
                if s in REG8:return [0x98+REG8[s]]
                return [0xde,lo(self.imm(s,u))]
        if op=='sub' and len(o)==1:
            s=o[0]
            if s in REG8:return [0x90+REG8[s]]
            return [0xd6,lo(self.imm(s,u))]
        if op in ('and','xor','or','cp') and len(o)==1:
            base={'and':0xa0,'xor':0xa8,'or':0xb0,'cp':0xb8}[op]; imm={'and':0xe6,'xor':0xee,'or':0xf6,'cp':0xfe}[op]
            s=o[0]
            if s in REG8:return [base+REG8[s]]
            return [imm,lo(self.imm(s,u))]
        if op in ('rl','rr','sla','sra','srl') and len(o)==1 and o[0] in REG8:
            base={'rl':0x10,'rr':0x18,'sla':0x20,'sra':0x28,'srl':0x38}[op]
            return [0xcb,base+REG8[o[0]]]
        if op in ('bit','res','set') and len(o)==2 and o[1] in REG8:
            n=self.imm(o[0],u)
            if not 0<=n<=7:raise AsmError('bit index')
            base={'bit':0x40,'res':0x80,'set':0xc0}[op]
            return [0xcb,base+n*8+REG8[o[1]]]
        if op=='in' and len(o)==2:
            d,s=o
            if d=='a' and is_indirect(s) and inner(s)!='c':return [0xdb,lo(self.imm(inner(s),u))]
            if is_indirect(s) and inner(s)=='c' and d in REG8:return [0xed,0x40+REG8[d]*8]
        if op=='out' and len(o)==2:
            d,s=o
            if is_indirect(d) and inner(d)!='c' and s=='a':return [0xd3,lo(self.imm(inner(d),u))]
            if is_indirect(d) and inner(d)=='c' and s in REG8:return [0xed,0x41+REG8[s]*8]
        raise AsmError(f'unsupported instruction: {op} {", ".join(o)}')

    def assemble(self,path:Path):
        self.load(path)
        for passno in (1,2):
            self.pc=0; self.origin=None; self.output=bytearray(); self.listing=[]
            for line in self.lines:
                before=self.pc
                try: data=self.parse_line(line,passno)
                except Exception as e: raise AsmError(f'{line.path}:{line.number}: {e}\n  {line.text}') from e
                # org changes pc inside parse_line. For ordinary output, append.
                if data:
                    if self.origin is None: raise AsmError('output before org')
                    if passno==2:
                        expected=self.pc-self.origin
                        if expected<0: raise AsmError('pc before origin')
                        if len(self.output)<expected:self.output.extend(b'\0'*(expected-len(self.output)))
                        if len(self.output)!=expected: raise AsmError('overlapping output')
                        self.output.extend(data); self.listing.append((self.pc,data,line))
                    self.pc+=len(data)
            if passno==1:
                # Keep symbols, reset only generated state.
                pass
        return bytes(self.output),self.origin,self.symbols,self.listing

def main(argv):
    if len(argv)<3:
        print('usage: z80asm.py input.asm output.bin [map.txt] [listing.txt]',file=sys.stderr);return 2
    asm=Assembler(); data,origin,symbols,listing=asm.assemble(Path(argv[1]))
    Path(argv[2]).write_bytes(data)
    if len(argv)>3:
        Path(argv[3]).write_text('\n'.join(f'{k} = 0x{v:04X}' for k,v in sorted(symbols.items(),key=lambda kv:(kv[1],kv[0])))+'\n')
    if len(argv)>4:
        lines=[]
        for pc,b,line in listing:
            hexs=' '.join(f'{x:02X}' for x in b)
            lines.append(f'{pc:04X}  {hexs:<30}  {line.text}')
        Path(argv[4]).write_text('\n'.join(lines)+'\n')
    print(f'assembled {len(data)} bytes at 0x{origin:04X} -> {argv[2]}')
    return 0
if __name__=='__main__':
    raise SystemExit(main(sys.argv))
