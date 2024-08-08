# This file contains the drf_spectacular annotations so we can document the user-login endpoints in Swagger

# extend_schema_view(
#     post=extend_schema(
#         request={
#             'application/json': {
#                 'type': 'object',
#                 'properties': {
#                     'username': {'type': 'string'},
#                     'password': {'type': 'string'},
#                 },
#                 'required': ['username', 'password'],
#             },
#         },
#         responses={
#             # 200: OpenApiTypes.OBJECT,
#             # 400: OpenApiTypes.OBJECT,
#         },
#     ),
# )(UserLoginView)