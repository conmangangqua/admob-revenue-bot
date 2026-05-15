import re

def update_looker_reader():
    try:
        with open("cookie.txt", "r", encoding="utf-8") as f:
            curl_text = f.read()
    except FileNotFoundError:
        print("Không tìm thấy file cookie.txt!")
        return

    # Extract Cookie
    cookie_match = re.search(r"-H 'Cookie: (.*?)'", curl_text)
    # Extract XSRF token
    xsrf_match = re.search(r"-H 'X-RAP-XSRF-TOKEN: (.*?)'", curl_text)
    # Extract payload
    payload_match = re.search(r"--data-raw '(.*?)'", curl_text, re.DOTALL)

    if not cookie_match or not xsrf_match or not payload_match:
        print("Không tìm thấy đủ thông tin (Cookie, XSRF, Payload) trong cookie.txt. Vui lòng copy lại cURL chuẩn từ Tab Network!")
        return

    new_cookie = cookie_match.group(1)
    new_xsrf = xsrf_match.group(1)
    new_payload = payload_match.group(1)

    with open("scripts/looker_reader.py", "r", encoding="utf-8") as f:
        code = f.read()

    # Replace values
    code = re.sub(r'DEFAULT_COOKIE\s*=\s*".*?"', f'DEFAULT_COOKIE = "{new_cookie}"', code)
    code = re.sub(r'DEFAULT_XSRF\s*=\s*".*?"', f'DEFAULT_XSRF = "{new_xsrf}"', code)
    code = re.sub(r'LOOKER_PAYLOAD\s*=\s*\"\"\"(.*?)\"\"\"', f'LOOKER_PAYLOAD = """{new_payload}"""', code, flags=re.DOTALL)

    with open("scripts/looker_reader.py", "w", encoding="utf-8") as f:
        f.write(code)

    print("Đã cập nhật tự động Cookie, XSRF Token và Payload vào scripts/looker_reader.py thành công!")

if __name__ == "__main__":
    update_looker_reader()
