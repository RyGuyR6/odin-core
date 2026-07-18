#!/usr/bin/env python3

import argparse

from odin_cli import doctor
from odin_cli import generate

parser = argparse.ArgumentParser(prog="odin")

sub = parser.add_subparsers(dest="command")

doctor_cmd = sub.add_parser("doctor")
doctor_cmd.set_defaults(func=lambda args: doctor.run())

generate_cmd = sub.add_parser("generate")
generate_sub = generate_cmd.add_subparsers(dest="type")

service_cmd = generate_sub.add_parser("service")
service_cmd.add_argument("name")
service_cmd.set_defaults(
    func=lambda args: generate.generate_service(args.name)
)


api_cmd = generate_sub.add_parser("api")
api_cmd.add_argument("name")
api_cmd.set_defaults(
    func=lambda args: generate.generate_api(args.name)
)


feature_cmd = generate_sub.add_parser("feature")
feature_cmd.add_argument("name")
feature_cmd.set_defaults(
    func=lambda args: generate.generate_feature(args.name)
)


crud_cmd = generate_sub.add_parser("crud")
crud_cmd.add_argument("name")
crud_cmd.set_defaults(
    func=lambda args: generate.generate_crud(args.name)
)


model_cmd = generate_sub.add_parser("model")
model_cmd.add_argument("name")
model_cmd.set_defaults(
    func=lambda args: generate.generate_model(args.name)
)


repository_cmd = generate_sub.add_parser("repository")
repository_cmd.add_argument("name")
repository_cmd.set_defaults(
    func=lambda args: generate.generate_repository(args.name)
)

args = parser.parse_args()

if hasattr(args, "func"):
    args.func(args)
else:
    parser.print_help()
