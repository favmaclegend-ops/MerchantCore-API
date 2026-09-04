# Organization Update

## Service creation

create services for organization.

creation `/org_services`\
requirement {\
organization_id=org_id,
name=service_data.name,\
 category=service_data.category,\
pricing_type=service_data.pricing_type,\
 price=service_data.price,\
 service_id = uuid.uuid4(),\
 description=service_data.description
}\

\
get_services `get_org_services`
