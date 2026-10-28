from fractions import Fraction
def number(value):
    if isinstance(value,dict) and set(value)=={'numerator','denominator'}:
        return float(Fraction(int(value['numerator']),int(value['denominator'])))
    return float(Fraction(str(value)))
def view(value,key=None):
    if isinstance(value,dict):
        if set(value)=={'numerator','denominator'}: return number(value)
        return {k:view(v,k) for k,v in value.items()}
    if isinstance(value,list): return [view(v,key) for v in value]
    if value is not None and key in {'duration','onset','starts','start','end','time'}:
        try: return number(value)
        except (ValueError,ZeroDivisionError): pass
    return value
