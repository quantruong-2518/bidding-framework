import { HttpModule } from '@nestjs/axios';
import { Module } from '@nestjs/common';
import { AclController } from './acl.controller';
import { AclService } from './acl.service';

@Module({
  imports: [HttpModule],
  controllers: [AclController],
  providers: [AclService],
  exports: [AclService],
})
export class AclModule {}
