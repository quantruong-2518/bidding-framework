import { IsOptional, IsString, MaxLength } from 'class-validator';

export class TriggerWorkflowDto {
  @IsOptional()
  @IsString()
  @MaxLength(200)
  taskQueue?: string;
}
