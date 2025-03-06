import oss2
import os
from dotenv import load_dotenv
load_dotenv()
def upload_file_to_oss(object_key, file_path):
    """
    上传文件到阿里云OSS，并返回文件的访问URL。

    :param access_key: 阿里云AccessKey ID
    :param secret_key: 阿里云AccessKey Secret
    :param endpoint: OSS服务的域名，例如 'http://oss-cn-hangzhou.aliyuncs.com'
    :param bucket_name: 存储空间名称
    :param object_key: 上传到OSS后的文件名称（可以包含目录）
    :param file_path: 本地文件路径
    :return: 文件的访问URL
    """
    endpoint = os.getenv('OSS_ENDPOINT')
    bucket_name = os.getenv('OSS_BUCKET_NAME')
    access_key = os.getenv('OSS_ACCESS_KEY')
    secret_key = os.getenv('OSS_SECRET_KEY')

    # 创建认证对象
    auth = oss2.Auth(access_key, secret_key)
    # 创建存储空间对象
    bucket = oss2.Bucket(auth, endpoint, bucket_name)

    # 上传文件
    with open(file_path, 'rb') as fileobj:
        result = bucket.put_object(object_key, fileobj)
        if result.status == 200:
            print("文件上传成功")
        else:
            print(f"文件上传失败，状态码：{result.status}")
            return None

    # 获取文件的访问URL
    # 注意：如果你的bucket是私有的，你可能需要生成一个带签名的URL
    url = f"https://{bucket_name}.{endpoint}/{object_key}"
    return url
