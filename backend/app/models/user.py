# # app/models/user.py # TEST: test for file use
# from pydantic import BaseModel, EmailStr, Field, ConfigDict # Added ConfigDict # TEST: test for file use
# from typing import Optional, List # TEST: test for file use
# from datetime import datetime, timezone # Added timezone # TEST: test for file use
# import uuid # Keep for potential use, but ID likely comes from Kinde # TEST: test for file use
# # TEST: test for file use
# # Basic properties shared by all User variations # TEST: test for file use
# class UserBase(BaseModel): # TEST: test for file use
#     # Using EmailStr ensures the email field is validated as an email # TEST: test for file use
#     email: EmailStr = Field(...) # Ellipsis means this field is required # TEST: test for file use
#     full_name: Optional[str] = None # Optional field # TEST: test for file use
#     is_active: bool = True # TEST: test for file use
#     # Roles etc. will be added later or handled via Kinde claims # TEST: test for file use
# # TEST: test for file use
#     # Pydantic V2 model config # TEST: test for file use
#     model_config = ConfigDict( # TEST: test for file use
#         from_attributes=True, # TEST: test for file use
#         populate_by_name=True, # TEST: test for file use
#     ) # TEST: test for file use
# # TEST: test for file use
# # Properties required when creating a user (might be handled by Kinde) # TEST: test for file use
# class UserCreate(UserBase): # TEST: test for file use
#     # Often, user creation details come from the auth provider (Kinde) # TEST: test for file use
#     # This model might be simple initially # TEST: test for file use
#     # Kinde ID will be set separately # TEST: test for file use
#     pass # TEST: test for file use
# # TEST: test for file use
# # Properties allowed when updating a user # TEST: test for file use
# class UserUpdate(BaseModel): # TEST: test for file use
#     full_name: Optional[str] = None # TEST: test for file use
#     is_active: Optional[bool] = None # TEST: test for file use
#     # is_deleted is not updated via this model # TEST: test for file use
#     # Add other updatable fields here # TEST: test for file use
# # TEST: test for file use
# # Base model for users stored in the database (includes common DB fields) # TEST: test for file use
# class UserInDBBase(UserBase): # TEST: test for file use
#     # ID field should store the Kinde User ID (string) # TEST: test for file use
#     # Removed default_factory as the ID comes from Kinde # TEST: test for file use
#     id: str = Field(..., alias="_id", description="Kinde User ID (Primary Key)") # MODIFIED # TEST: test for file use
# # TEST: test for file use
#     created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc)) # TEST: test for file use
#     updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc)) # TEST: test for file use
# # TEST: test for file use
#     # --- RBAC Changes Below --- # TEST: test for file use
#     is_deleted: bool = Field(default=False, description="Flag for soft delete status") # ADDED # TEST: test for file use
#     # --- RBAC Changes Above --- # TEST: test for file use
# # TEST: test for file use
#     # Inherit model_config from Base, add specifics if needed # TEST: test for file use
#     model_config = ConfigDict( # TEST: test for file use
#         # from_attributes = True # Inherited # TEST: test for file use
#         # populate_by_name = True # Inherited # TEST: test for file use
#         arbitrary_types_allowed = True # Allow complex types if needed later # TEST: test for file use
#     ) # TEST: test for file use
# # TEST: test for file use
# # Final User model representing data coming from the database # TEST: test for file use
# class User(UserInDBBase): # TEST: test for file use
#     # Inherits all fields including is_deleted # TEST: test for file use
#     pass # TEST: test for file use
# # TEST: test for file use
# # You might also have a model for user data returned by the API # TEST: test for file use
# # class UserPublic(UserBase): # TEST: test for file use
# #     id: str # Exclude sensitive fields if necessary # TEST: test for file use
# # TEST: test for file use
