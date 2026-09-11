#构建函数,实现加减乘除功能
def calculator(a,b,operation):
    if operation == 'add':
        return a+b
    elif operation == 'subtract':
        return a-b
    elif operation == 'multiply':
        return a*b
    elif operation == 'divide':
        if b == 0:
            raise ValueError("除数不能为0")
        return a/b
    else:
        raise ValueError("不支持的操作符")


if __name__=='__main__':
    print(calculator(10, 5, "add"))

    try:
        calculator(10, 0, "divide")
    except ValueError as e:
        print(e)

    try:
        calculator(10, 5, "abc")
    except ValueError as e:
        print(e)

