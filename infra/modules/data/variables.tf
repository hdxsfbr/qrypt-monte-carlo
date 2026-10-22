variable "name" {
  description = "Name prefix, qmc-<environment>."
  type        = string
}

variable "table_capacity" {
  description = "Provisioned read and write units for the table."
  type        = number
}

variable "index_capacity" {
  description = "Provisioned read and write units for the by_created index."
  type        = number
}
