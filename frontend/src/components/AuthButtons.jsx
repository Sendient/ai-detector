import React from 'react';
import { useKindeAuth } from '@kinde-oss/kinde-auth-react';
import { LoginLink, RegisterLink, LogoutLink } from '@kinde-oss/kinde-auth-react/components';

const AuthButtons = () => {
  const { user, isAuthenticated, isLoading } = useKindeAuth();

  if (isLoading) {
    return <div>Loading...</div>;
  }

  if (isAuthenticated) {
    return (
      <div className="flex items-center gap-4">
        <span className="text-sm">
          Welcome, {user.given_name || user.email}
        </span>
        <LogoutLink className="btn btn-outline btn-sm">
          Sign out
        </LogoutLink>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-4">
      <LoginLink className="btn btn-primary btn-sm">
        Sign in
      </LoginLink>
      <RegisterLink className="btn btn-outline btn-sm">
        Sign up
      </RegisterLink>
    </div>
  );
};

export default AuthButtons; 