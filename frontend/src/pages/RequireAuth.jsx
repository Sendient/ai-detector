import React from 'react';
import { useKindeAuth } from '@kinde-oss/kinde-auth-react';
import { InformationCircleIcon } from '@heroicons/react/24/outline';

function RequireAuth() {
  const { login } = useKindeAuth();
  return (
    <div className="flex flex-col items-center justify-center min-h-screen">
      <div className="alert alert-info shadow-lg max-w-lg w-full">
        <InformationCircleIcon className="h-6 w-6 stroke-current shrink-0 mr-2" />
        <div>
          <h3 className="font-bold mb-1">Login Required</h3>
          <div className="text-sm mb-2">Please log in to access this page.</div>
          <button className="btn btn-primary" onClick={login}>Log In</button>
        </div>
      </div>
    </div>
  );
}

export default RequireAuth; 