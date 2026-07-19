
from jsonpath import jsonpath

def extract(resp, attr_name, exp):
    """提取请求返回值中指定属性

    Args:
        resp (httpx.Response): 请求返回结构体
        attr_name (str): 属性名
        exp (str): 获取属性的表达式，适配jsonpath

    Returns:
        any: 获取的属性值
    """
    try:
        data = resp.json()
    except Exception:
        data = {}

    if attr_name == "json":
        attr = data
    else:
        attr = getattr(resp, attr_name)
    res = jsonpath(attr, exp)   # jsonpath返回是list格式
    return res[0]