"""Keep stock JWT validation separate from Databricks proxy OAuth headers."""

TOKEN_TRANSPORT_SCRIPT = """const stockFetch=window.fetch.bind(window);window.fetch=(input,init={})=>{
  const url=new URL(typeof input==='string'?input:input.url,window.location.origin);
  if(url.origin===window.location.origin&&(url.pathname==='/graphql/'||url.pathname.startsWith('/api/imports/'))){
    const headers=new Headers(init.headers||(input instanceof Request?input.headers:undefined));
    const jwt=headers.get('Authorization');
    if(jwt){headers.set('X-OpenContracts-Authorization',jwt);headers.delete('Authorization');}
    init={...init,headers};
  }return stockFetch(input,init);};"""


class BackendTokenHeaderMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = request.META.get("HTTP_X_OPENCONTRACTS_AUTHORIZATION")
        if (
            request.path == "/graphql/" or request.path.startswith("/api/imports/")
        ) and token:
            request.META["HTTP_AUTHORIZATION"] = token
        return self.get_response(request)
