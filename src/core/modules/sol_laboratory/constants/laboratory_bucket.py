"""The environment variables of the laboratory files bucket, and the sizes its objects are written and read in."""

# Odoo's access key and secret key, which reach the laboratory files bucket only.
ACCESS_KEY_VARIABLE = "BUCKET_LABORATORY_ACCESS_KEY"
SECRET_KEY_VARIABLE = "BUCKET_LABORATORY_SECRET_KEY"
# The bucket's name.
NAME_VARIABLE = "BUCKET_LABORATORY_NAME"
# The address Odoo calls the bucket at.
ADDRESS_VARIABLE = "BUCKET_LABORATORY_ADDRESS"
# The address presigned addresses are made for: computers and the editing service reach the bucket there.
PUBLIC_ADDRESS_VARIABLE = "BUCKET_LABORATORY_PUBLIC_ADDRESS"
# The region the keys sign for.
REGION_VARIABLE = "BUCKET_LABORATORY_REGION"
# The size of every part of a multipart upload but the last.
PART_SIZE = 16 * 1024 * 1024
# The size of the chunks an object is read in.
READ_CHUNK_SIZE = 8 * 1024 * 1024
FILESTORE_VARIABLE = "BUCKET_FILESTORE"
FILESTORE_PREFIX = "filestore"
FILESTORE_GC_GRACE = 24 * 60 * 60
