from datetime import datetime

def get_time(r_info:str):
    print(r_info)
    now = datetime.now()
    return(now.strftime('%Y-%m-%d %H:%M:%S'))
