import pytest
from tksessentials.security import Crypto

AES_SECRET = "ZufDdKmoYgBv272G0DQWqz8Ng9ewM+IMGIMzkRQUoVNujiCHfdD4EULwXtn5fvwL"

@pytest.mark.parametrize("message", ["test", "123908234ÖÄ$ASDFdd", "äjklöèü"])
def test_encrypt_and_decrypt_text_message(monkeypatch, message):
    monkeypatch.setenv("AES_SECRET", AES_SECRET)
    crypto = Crypto()

    encrypted_message = crypto.encrypt_as_text(message)
    decrypted_message = crypto.decrypt_as_text(encrypted_message)

    assert decrypted_message == message

@pytest.mark.parametrize("message", ["firstname.name@domain.com"])
def test_encrypt_and_decrypt_email_address(monkeypatch, message):
    monkeypatch.setenv("AES_SECRET", AES_SECRET)
    crypto = Crypto()

    encrypted_message = crypto.encrypt_as_text(message)
    decrypted_message = crypto.decrypt_as_text(encrypted_message)

    assert decrypted_message == message

# FAILY - NEEDS TO BE FIXED
# @pytest.mark.parametrize("ip_address, blocking_reason", [("155.255.452.55", BlockedIpReasonType.EXCESSIVE_FAILED_LOGIN_ATTEMPTS)])
# def test_block_ip_address(ip_address: str, blocking_reason: BlockedIpReasonType):
#     ipSecurity = IPSecurity()

#     assert ipSecurity.block_ip(ip_address, blocking_reason) is True
#     assert ipSecurity.is_ip_blocked(ip_address) is True
#     assert ipSecurity.unblock_ip(ip_address) is True
#     assert ipSecurity.is_ip_blocked(ip_address) is False
