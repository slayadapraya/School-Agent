"""Public listener rules, independent of spoofable Host/forwarding headers."""
import re

def acceptable_password(password,username=''):
    if not isinstance(password,str) or not 12<=len(password)<=256:return False
    value=password.casefold()
    if value in {'password1234','password12345','password123456','123456789012','abcdefghijkl','qwertyuiop12','letmein123456','admin1234567','schoolagent123','schoolagent1234'}:return False
    if username and re.fullmatch(re.escape(username.casefold())+r'[\d\W_]*',value):return False
    if len(set(value))<5:return False
    return True

MESSAGE='Public sign-in requires a stronger password of at least 12 characters. Set it in Account settings using the local or private connection first.'
